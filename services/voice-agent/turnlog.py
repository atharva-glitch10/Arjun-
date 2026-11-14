"""Per-turn timing log: one JSON line per turn to stdout and eval/results/turns.jsonl.

No audio and no secrets are logged. Timestamps are epoch seconds from the LiveKit session events:
  t_end_of_speech   user_state_changed speaking -> listening (VAD end of speech, not the exact last sound)
  t_final_transcript  first final user_input_transcribed of the turn
  t_reasoning_start the agent handed the transcript to reasoning (after the end-of-turn decision)
  t_reasoning_done  reasoning /turn answered (measured around the HTTP call in on_user_turn_completed)
  t_agent_speaking  agent_state_changed -> speaking (playout of the first TTS audio starts)

A turn is identified by its transcript, not by whichever event arrives next. The first real-speech test
(2026-10-24) showed why: the user spoke again before the previous reply was ready, and a log that kept
a single "current turn" paired replies and audio with the wrong sentence. Here every turn keeps its own
index from the first final transcript until its audio starts (or it is skipped), however many are open.

The stream transport exposes the first complete, already-guarded reply sentence, not raw LLM token deltas.
`t_llm_first_token` records that first safe output chunk so the voice pipeline can measure/prewarm against it.
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("arjun.turns")

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "eval" / "results" / "turns.jsonl"
EOS_WINDOW_S = 5.0  # an end-of-speech this close to a final transcript belongs to it
_EPOCH0 = 1_700_000_000  # turn numbers count from here, so they stay small enough for a screen attribute


class TurnLog:
    # Why a turn has no "speaking" time (or that it has one). Written to every line as "outcome".
    OUTCOMES = ("spoken", "interrupted", "tts_failed", "stale", "no_reply", "not_spoken")

    @staticmethod
    def base_for(epoch_s: float) -> int:
        """Where a session's turn numbers start. Time-derived (2 numbers per second of wall clock), so a browser that
        drops and rejoins (a NEW LiveKit job, a new TurnLog) continues ABOVE the old session: the app compares
        `arjun.turn` numbers (a safety screen is dismissed "up to turn N"), so they must never go back to 1."""
        return max(0, int(epoch_s) - _EPOCH0) * 2

    def __init__(
        self, language_selected: str, path: Path = DEFAULT_PATH, session: str = "", start: int = 0,
        stt_provider: str = "gnani", tts_provider: str = "gnani",
    ) -> None:
        self.language_selected = language_selected
        self.stt_provider, self.tts_provider = stt_provider, tts_provider  # which speech services made this row
        self.path = path
        self.session = session  # the LiveKit job id; one JSON line per turn carries it
        self.start = start
        self.index = start
        self._open: dict[int, dict] = {}  # turns not yet written, by index
        self._taken: set[int] = set()  # handed to reasoning (no longer collecting finals)
        self._last_eos: float | None = None
        self._speaking: int | None = None  # the turn whose reply is being spoken now
        self._active_speech_turn: int | None = None
        self._barge_in_started_at: float | None = None
        self.tts_prewarm = "miss"

    # ---- helpers -----------------------------------------------------------------------------
    def _new(self) -> dict:
        self.index += 1
        turn = {"turn": self.index, "n": self.index - self.start, "language_selected": self.language_selected,
                "action_type": "", "ignored_media": False,
                "stt_provider": self.stt_provider, "tts_provider": self.tts_provider,
                "tts_prewarm": self.tts_prewarm}
        if self.session:
            turn["session"] = self.session
        self._open[self.index] = turn
        return turn

    def _collecting(self) -> dict | None:
        """The turn still gathering final transcripts (not yet taken by reasoning), if any."""
        for i in sorted(self._open):
            if i not in self._taken:
                return self._open[i]
        return None

    def active_turn(self) -> int | None:
        """The newest turn currently being handled by reasoning."""
        return max(self._taken, default=None)

    def bump(self) -> int:
        """A new, larger event number for something that is not a spoken turn (a delivery, a close), so the app
        can tell it from the previous screen. No row is written."""
        self.index += 1
        return self.index

    # ---- events -------------------------------------------------------------------------------
    def end_of_speech(self, t: float) -> None:
        """The LATEST end of speech before reasoning starts wins: in a long story she pauses many times, and only the
        last pause is when she stopped (the first one made a 42 s monologue look like a 33 s delay, 2026-10-31)."""
        cur = self._collecting()
        last_final = None if cur is None else cur.get("t_last_final", cur["t_final_transcript"])
        if cur is not None and 0 <= t - last_final <= EOS_WINDOW_S:
            cur["t_end_of_speech"] = t  # the final transcript arrived first
        else:
            self._last_eos = t

    def final_transcript(self, t: float, text: str, language: str | None) -> int:
        cur = self._collecting()
        if cur is not None:  # several finals before the turn is taken: keep the first time, join the text
            cur["transcript"] += " " + text
            cur["t_last_final"] = t
            if self._last_eos is not None and 0 <= t - self._last_eos <= EOS_WINDOW_S:
                cur["t_end_of_speech"] = self._last_eos  # the end of speech arrived before this final
                self._last_eos = None
            return int(cur["turn"])
        turn = self._new()
        turn.update(t_final_transcript=t, transcript=text, language_detected=language)
        if self._last_eos is not None and 0 <= t - self._last_eos <= EOS_WINDOW_S:
            turn["t_end_of_speech"] = self._last_eos
        self._last_eos = None
        return int(turn["turn"])

    def clip_transcript(self, t_eos: float, t_final: float, text: str, language: str | None) -> int:
        """A push-to-record clip through REST STT: the EOS is when the recording stopped, the final is when Prisma
        answered. There is no VAD end-of-speech event and no interim on this path, so both times are set explicitly
        (otherwise every REST turn logged the four latency fields as null and complete=False)."""
        turn = self._new()
        turn.update(t_final_transcript=t_final, t_last_final=t_final, t_end_of_speech=t_eos,
                    transcript=text, language_detected=language)
        return int(turn["turn"])

    def reasoning_started(self, transcript: str, t: float | None = None, source: str = "voice") -> int:
        """The agent took this transcript for reasoning: claim its turn and return the turn index.

        A tapped answer ("tap") has no speech: it always gets its own turn and never claims a spoken
        sentence that is still being collected.
        """
        cur = self._collecting() if source == "voice" else None
        if cur is None:  # a tap, or no final was seen for it (should not happen)
            cur = self._new()
            cur.update(transcript=transcript.strip())
            if source == "tap" and t is not None:
                cur["t_final_transcript"] = t  # the tap itself is the "transcript" moment
        cur["source"] = source
        if t is not None:
            cur["t_reasoning_start"] = t
        self._taken.add(int(cur["turn"]))
        return int(cur["turn"])

    def reasoning_done(
        self, idx: int, t: float, reply: str, mode: str, reasoning_ms: float | None = None,
        intent: str = "", source: str = "", action_type: str = "",
    ) -> None:
        if idx in self._open:
            self._open[idx].update(t_reasoning_done=t, reply=reply, mode=mode, action_type=action_type)
            if intent:
                self._open[idx]["intent"] = intent
            if source:  # rules | llm: who wrote the answer
                self._open[idx]["source"] = source
            if reasoning_ms is not None:  # the /turn round trip itself, apart from the end-of-turn wait
                self._open[idx]["reasoning_ms"] = round(reasoning_ms)

    def llm_first_token(self, idx: int, t: float) -> None:
        if idx in self._open and self._open[idx].get("t_llm_first_token") is None:
            self._open[idx]["t_llm_first_token"] = t

    def set_tts_prewarm(self, status: str, idx: int | None = None) -> None:
        if status not in ("hit", "miss"):
            raise ValueError("tts prewarm status must be hit or miss")
        if idx is None:
            self.tts_prewarm = status
        elif idx in self._open:
            self._open[idx]["tts_prewarm"] = status

    def speaking_for(self, idx: int, t: float | None = None) -> None:
        """The reply for turn `idx` is about to be spoken: the next playout start belongs to it."""
        self._speaking = idx
        if idx in self._open:
            self._open[idx]["t_say_start"] = time.time() if t is None else t

    def speaking_turn(self) -> int | None:
        return self._speaking

    def not_spoken(self, idx: int, reason: str) -> None:
        """The reply for turn `idx` never played (she spoke again, or TTS failed): write the line now, with the reason."""
        if self._speaking == idx:
            self._speaking = None
        self.speech_finished(idx)
        if idx in self._open:
            self._open[idx]["outcome"] = reason
            self.flush(idx)

    def agent_speaking(self, t: float) -> None:
        idx, self._speaking = self._speaking, None
        if idx is None or idx not in self._open:
            return  # speech that is not a reply to a user turn
        self._active_speech_turn = idx
        self._open[idx]["t_agent_speaking"] = t
        self.flush(idx)

    def user_started_speaking(self, t: float) -> None:
        """Start a barge-in timer only while a reply's audio is active."""
        if self._active_speech_turn is not None:
            self._barge_in_started_at = t

    def agent_stopped_speaking(self, t: float) -> None:
        idx, started = self._active_speech_turn, self._barge_in_started_at
        self._barge_in_started_at = None
        if idx is None or started is None:
            return
        event = {
            "metric_event": "barge_in", "turn": idx, "t_event": t,
            "barge_in_stop_ms": max(0, round((t - started) * 1000)),
        }
        if self.session:
            event["session"] = self.session
        self._append(event)

    def speech_finished(self, idx: int) -> None:
        if self._active_speech_turn == idx:
            self._active_speech_turn = None
            self._barge_in_started_at = None

    def is_stale(self, idx: int) -> bool:
        """True when the user has said something newer than turn `idx` (a later final transcript)."""
        return self.index > idx

    def ignore_collected(self, reason: str) -> None:
        """A transcript that was not for Arjun (the video's own audio in media mode): write the row WITHOUT the words."""
        cur = self._collecting()
        if cur is not None:
            cur["transcript"] = ""
            cur["skipped"] = cur["outcome"] = reason
            cur["ignored_media"] = True
            self.flush(int(cur["turn"]))

    def skip(self, idx: int, reason: str) -> None:
        if idx in self._open:
            self._open[idx]["skipped"] = reason
            self._open[idx]["outcome"] = reason
            self.flush(idx)

    def close(self) -> None:
        """Session ended: write every turn that never got audio as incomplete."""
        for idx in sorted(self._open):
            self.flush(idx)

    # ---- output -------------------------------------------------------------------------------
    def flush(self, idx: int) -> dict | None:
        turn = self._open.pop(idx, None)
        self._taken.discard(idx)
        if turn is None:
            return None
        # a tapped turn has no speech: the tap itself marks its start
        start = turn.get("t_end_of_speech") or (turn.get("t_final_transcript") if turn.get("source") == "tap" else None)
        turn.setdefault("t_last_final", turn.get("t_final_transcript"))
        for key in ("eos_to_final_ms", "final_to_llm_first_token_ms", "llm_to_first_audio_ms", "eos_to_speaking_ms"):
            turn.setdefault(key, None)
        for name, a, b in (
            ("eos_to_final_ms", "t_end_of_speech", "t_final_transcript"),
            ("final_to_llm_first_token_ms", "t_final_transcript", "t_llm_first_token"),
            ("llm_to_first_audio_ms", "t_llm_first_token", "t_agent_speaking"),
            ("endpointing_ms", "t_last_final", "t_reasoning_start"),  # from the LAST final: she may talk on for a minute
            ("final_to_reasoning_ms", "t_final_transcript", "t_reasoning_done"),
            ("reasoning_to_audio_ms", "t_reasoning_done", "t_agent_speaking"),
            ("eos_to_audio_ms", "t_end_of_speech", "t_agent_speaking"),
            ("tts_first_audio_ms", "t_say_start", "t_agent_speaking"),
        ):
            if turn.get(a) is not None and turn.get(b) is not None:
                turn[name] = round((turn[b] - turn[a]) * 1000)
        if "eos_to_audio_ms" in turn:
            turn["eos_to_speaking_ms"] = turn["eos_to_audio_ms"]  # the name used in the write-up
        if "t_agent_speaking" in turn:
            turn["outcome"] = "spoken"
        elif "outcome" not in turn:
            turn["outcome"] = "not_spoken" if "reply" in turn else "no_reply"
        turn["complete"] = start is not None and "t_agent_speaking" in turn
        self._append(turn)
        return turn

    def _append(self, turn: dict) -> None:
        line = json.dumps(turn, ensure_ascii=False)
        logger.info("turn %s", line)
        print("TURN " + line, flush=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
