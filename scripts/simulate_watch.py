"""Post made-up watch samples to the demo household (a SYNTHETIC feed; no watch is paired).

  python scripts/simulate_watch.py                 # print what would be posted, change nothing
  python scripts/simulate_watch.py --apply         # post one set of samples now
  python scripts/simulate_watch.py --apply --every 60   # keep posting every 60 s (Ctrl+C to stop)

Raw values only: steps, heart rate and sleep minutes. No target, score, alert or advice.
Reads CORE_API_URL (default http://127.0.0.1:8000) and CORE_API_KEY from the environment/.env; the key is
never printed.
"""

import argparse
import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path


def _load_env() -> None:
    """Read the root .env without printing or exporting secrets beyond this process."""
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def samples(now: float) -> list[dict[str, object]]:
    """Plausible synthetic numbers. Nothing here is a measurement of a real person."""
    hour = time.localtime(now).tm_hour
    awake = 6 <= hour < 22
    return [
        {"kind": "steps", "value": random.randint(300, 1800) if awake else random.randint(0, 200)},
        {"kind": "heart_rate", "value": random.randint(62, 88) if awake else random.randint(52, 66)},
        {"kind": "sleep_minutes", "value": random.randint(330, 470)},
    ]


def post(base: str, key: str, user_id: int, body: dict[str, object]) -> dict[str, object]:
    req = urllib.request.Request(
        f"{base.rstrip('/')}/users/{user_id}/watch-samples",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as res:  # noqa: S310 - local demo URL
        return json.loads(res.read())


def main(argv: list[str] | None = None) -> int:
    _load_env()
    ap = argparse.ArgumentParser(description="A synthetic watch feed for the demo household.")
    ap.add_argument("--user", type=int, default=1)
    ap.add_argument("--base", default=os.environ.get("CORE_API_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--apply", action="store_true", help="really post (default is a dry run)")
    ap.add_argument("--every", type=int, default=0, help="keep posting every N seconds")
    args = ap.parse_args(argv)
    key = os.environ.get("CORE_API_KEY", "")
    if args.apply and not key:
        print("CORE_API_KEY is not set; refusing to post.", file=sys.stderr)
        return 2
    while True:
        rows = samples(time.time())
        if not args.apply:
            print("WOULD POST (synthetic watch):", json.dumps(rows))
            print("DRY RUN: nothing was sent. Add --apply to post.")
            return 0
        for row in rows:
            got = post(args.base, key, args.user, row)
            print(f"posted {got['kind']}={got['value']} {got['unit']} for user {got['user_id']}")
        if args.every <= 0:
            return 0
        time.sleep(args.every)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
