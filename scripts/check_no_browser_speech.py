"""Fail if any browser speech API is used by the web app (T6: the demo must speak through LiveKit + Gnani).

Usage: python scripts/check_no_browser_speech.py   (exit 1 and the offending lines if anything is found)
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"SpeechRecognition|webkitSpeechRecognition|speechSynthesis|SpeechSynthesisUtterance")
SCAN = [ROOT / "web" / "src", ROOT / "web" / "index.html"]


def find_hits() -> list[str]:
    hits = []
    files = [f for target in SCAN for f in ([target] if target.is_file() else target.rglob("*")) if f.is_file()]
    for f in files:
        if f.suffix not in {".ts", ".tsx", ".js", ".jsx", ".html", ".css"}:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if PATTERN.search(line):
                hits.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()}")
    return hits


if __name__ == "__main__":
    found = find_hits()
    print("\n".join(found) if found else "no browser speech API found in web/src or web/index.html")
    sys.exit(1 if found else 0)
