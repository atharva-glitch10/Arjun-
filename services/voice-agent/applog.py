"""Direct file log for the voice worker and its job processes.

The first real-speech test (2026-10-24) left logs/voice-agent.log without a single line from the
session: the job subprocess's console output goes through dev-up.ps1's pipe into Add-Content and
stopped arriving after the session started. A FileHandler on the root logger writes from inside every
process, so a missing console line no longer means a missing log.

No audio, transcripts of other people, or secrets are logged here; only library log records.
"""

import json
import logging
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "logs" / "voice-agent.app.log"
FORMAT = "%(asctime)s %(process)d %(levelname)s %(name)s - %(message)s"
_STANDARD = set(vars(logging.LogRecord("x", 0, "x", 0, "x", None, None))) | {"message", "asctime", "taskName"}


class _Formatter(logging.Formatter):
    """LiveKit logs its structured fields (agent_name, job_id, ...) as record extras: keep them."""

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        extra = {k: v for k, v in vars(record).items() if k not in _STANDARD and not k.startswith("_")}
        if extra:
            line += " " + json.dumps(extra, ensure_ascii=False, default=str)[:1500]
        return line


def setup_file_log(path: Path | None = None) -> Path:
    """Attach one append-mode FileHandler for `path` to the root logger (idempotent per process)."""
    target = Path(path or DEFAULT_PATH).resolve()
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and Path(h.baseFilename) == target:
            return target
    target.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(target, mode="a", encoding="utf-8")
    handler.setFormatter(_Formatter(FORMAT))
    root.addHandler(handler)
    return target
