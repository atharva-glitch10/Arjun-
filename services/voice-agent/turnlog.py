"""Per-turn timing log: one JSON line per turn to stdout and eval/results/turns.jsonl.

No audio and no secrets are logged. Timestamps are epoch seconds from the LiveKit session events:
  t_end_of_speech   user_state_changed speaking -> listening (VAD end of speech, not the exact last sound)
  t_final_transcript  first final user_input_transcribed of the turn
  t_reasoning_done  reasoning /turn answered (measured around the HTTP call in on_user_turn_completed)
  t_agent_speaking  agent_state_changed -> speaking (playout of the first TTS audio starts)
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("arjun.turns")

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "eval" / "results" / "turns.jsonl"


class TurnLog:
    def __init__(self, language_selected: str, path: Path = DEFAULT_PATH) -> None:
        self.language_selected = language_selected
        self.path = path
        self.index = 0
        self._turn: dict | None = None

    def _ensure(self) -> dict:
        if self._turn is None:
            self.index += 1
            self._turn = {"turn": self.index, "language_selected": self.language_selected}
        return self._turn

    def end_of_speech(self, t: float) -> None:
        if self._turn is not None and "t_agent_speaking" not in self._turn:
            self.flush()  # previous turn never got audio; record it as incomplete
        self._ensure()["t_end_of_speech"] = t

    def final_transcript(self, t: float, text: str, language: str | None) -> None:
        turn = self._ensure()
        if "t_final_transcript" in turn:  # several finals in one turn: keep the first time, join the text
            turn["transcript"] += " " + text
            return
        turn.update(t_final_transcript=t, transcript=text, language_detected=language)

    def reasoning_done(self, t: float, reply: str, mode: str) -> None:
        turn = self._ensure()
        turn.update(t_reasoning_done=t, reply=reply, mode=mode)

    def agent_speaking(self, t: float) -> None:
        if self._turn is None or "t_reasoning_done" not in self._turn:
            return  # speech that is not a reply to a user turn
        self._turn["t_agent_speaking"] = t
        self.flush()

    def flush(self) -> dict | None:
        turn, self._turn = self._turn, None
        if turn is None:
            return None
        start = turn.get("t_end_of_speech")
        for name, a, b in (
            ("eos_to_final_ms", "t_end_of_speech", "t_final_transcript"),
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
