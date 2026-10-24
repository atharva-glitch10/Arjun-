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
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("arjun.turns")

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "eval" / "results" / "turns.jsonl"
EOS_WINDOW_S = 5.0  # an end-of-speech this close to a final transcript belongs to it


class TurnLog:
    def __init__(self, language_selected: str, path: Path = DEFAULT_PATH) -> None:
        self.language_selected = language_selected
        self.path = path
        self.index = 0
        self._open: dict[int, dict] = {}  # turns not yet written, by index
        self._taken: set[int] = set()  # handed to reasoning (no longer collecting finals)
        self._last_eos: float | None = None
        self._speaking: int | None = None  # the turn whose reply is being spoken now

    # ---- helpers -----------------------------------------------------------------------------
    def _new(self) -> dict:
        self.index += 1
        turn = {"turn": self.index, "language_selected": self.language_selected}
        self._open[self.index] = turn
        return turn

    def _collecting(self) -> dict | None:
        """The turn still gathering final transcripts (not yet taken by reasoning), if any."""
        for i in sorted(self._open):
            if i not in self._taken:
                return self._open[i]
        return None

    # ---- events -------------------------------------------------------------------------------
    def end_of_speech(self, t: float) -> None:
        cur = self._collecting()
        if cur is not None and "t_end_of_speech" not in cur and 0 <= t - cur["t_final_transcript"] <= EOS_WINDOW_S:
            cur["t_end_of_speech"] = t  # the final transcript arrived first
        else:
            self._last_eos = t

    def final_transcript(self, t: float, text: str, language: str | None) -> int:
        cur = self._collecting()
        if cur is not None:  # several finals before the turn is taken: keep the first time, join the text
            cur["transcript"] += " " + text
            return int(cur["turn"])
        turn = self._new()
        turn.update(t_final_transcript=t, transcript=text, language_detected=language)
        if self._last_eos is not None and 0 <= t - self._last_eos <= EOS_WINDOW_S:
            turn["t_end_of_speech"] = self._last_eos
        self._last_eos = None
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
        self, idx: int, t: float, reply: str, mode: str, reasoning_ms: float | None = None
    ) -> None:
        if idx in self._open:
            self._open[idx].update(t_reasoning_done=t, reply=reply, mode=mode)
            if reasoning_ms is not None:  # the /turn round trip itself, apart from the end-of-turn wait
                self._open[idx]["reasoning_ms"] = round(reasoning_ms)

    def speaking_for(self, idx: int) -> None:
        """The reply for turn `idx` is about to be spoken: the next playout start belongs to it."""
        self._speaking = idx

    def agent_speaking(self, t: float) -> None:
        idx, self._speaking = self._speaking, None
        if idx is None or idx not in self._open:
            return  # speech that is not a reply to a user turn
        self._open[idx]["t_agent_speaking"] = t
        self.flush(idx)

    def is_stale(self, idx: int) -> bool:
        """True when the user has said something newer than turn `idx` (a later final transcript)."""
        return self.index > idx

    def skip(self, idx: int, reason: str) -> None:
        if idx in self._open:
            self._open[idx]["skipped"] = reason
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
        for name, a, b in (
            ("eos_to_final_ms", "t_end_of_speech", "t_final_transcript"),
            ("endpointing_ms", "t_final_transcript", "t_reasoning_start"),
            ("final_to_reasoning_ms", "t_final_transcript", "t_reasoning_done"),
            ("reasoning_to_audio_ms", "t_reasoning_done", "t_agent_speaking"),
            ("eos_to_audio_ms", "t_end_of_speech", "t_agent_speaking"),
        ):
            if turn.get(a) is not None and turn.get(b) is not None:
                turn[name] = round((turn[b] - turn[a]) * 1000)
        turn["complete"] = start is not None and "t_agent_speaking" in turn
        line = json.dumps(turn, ensure_ascii=False)
        logger.info("turn %s", line)
        print("TURN " + line, flush=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return turn
