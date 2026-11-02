"""Seed the synthetic demo household (user 1) with the apps she can open by voice. DRY RUN unless --apply.

  python scripts/seed_apps.py                 # print what would be added, change nothing
  python scripts/seed_apps.py --apply         # add the missing entries (safe to run twice: existing labels are kept)
  python scripts/seed_apps.py --user 2 --apply

Goes through core-api (so every value is validated like a family entry), never touches a database file.
Reads CORE_API_URL (default http://127.0.0.1:8000) and CORE_API_KEY from the environment or the root .env; the key
is never printed. The numbers are made up. The ids below were each checked once on 2026-11-02 (see STATUS.md).
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONTACT = ("चंद्रकांत", "मुलगा", "00000 00003")  # made up, not a real number

# (kind, label, value, spoken names). value for "whatsapp" is filled in with the contact id.
LINKS: list[tuple[str, str, str, list[str]]] = [
    # public Marathi bhakti-geete playlist "Super Hit Pahateche Bhakti | Prabhat Geet" (Wings Marathi Bhakti)
    ("youtube_playlist", "भक्तिगीते", "PL01mceoBxHCiCj28l-viryuhBh7nXsqZN", ["भक्तिगीते", "भजन", "देवाची गाणी", "bhajan"]),
    # ABP MAJHA (Marathi news) live channel
    ("youtube_channel_live", "एबीपी माझा लाईव्ह", "UCH7nv1A9xIrAifZJNvt7cgA", ["बातम्या", "माझा", "एबीपी माझा", "news"]),
    ("rss", "एबीपी माझा", "https://marathi.abplive.com/home/feed", []),
    ("rss", "बीबीसी मराठी", "https://feeds.bbci.co.uk/marathi/rss.xml", []),
    ("whatsapp", "चंद्रकांत", "", ["चंद्रकांत"]),
    ("link", "नातवाचे फोटो", "https://photos.google.com/", ["नातवाचे फोटो", "फोटो"]),  # placeholder: the family pastes a real album
]


def _load_env() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, _, value = line.partition("=")
            if name.strip() in ("CORE_API_URL", "CORE_API_KEY"):
                os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def _call(method: str, path: str, body: object | None = None):  # type: ignore[no-untyped-def]
    base = os.environ.get("CORE_API_URL", "http://127.0.0.1:8000").rstrip("/")
    headers = {"Content-Type": "application/json"}
    if os.environ.get("CORE_API_KEY"):
        headers["X-API-Key"] = os.environ["CORE_API_KEY"]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - the local core-api
        return json.loads(r.read() or "null")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--user", type=int, default=1)
    args = ap.parse_args()
    _load_env()
    uid = args.user
    try:
        contacts = _call("GET", f"/users/{uid}/contacts")
        have = {(link["kind"], link["label"]) for link in _call("GET", f"/users/{uid}/app-links")}
    except (urllib.error.URLError, OSError) as exc:
        print(f"core-api is not reachable ({exc}). Start it first (scripts/dev-up.ps1).")
        return 1
    contact = next((c for c in contacts if c["name"] == CONTACT[0]), None)
    todo = [(k, label, v, names) for k, label, v, names in LINKS if (k, label) not in have]
    print(f"user {uid}: {len(todo)} entr{'y' if len(todo) == 1 else 'ies'} to add" + ("" if args.apply else " (dry run)"))
    for kind, label, value, _ in todo:
        print(f"  + {kind:22} {label}  {value or '(the contact ' + CONTACT[0] + ')'}")
    if not args.apply:
        return 0
    if any(k == "whatsapp" for k, *_ in todo) and contact is None:
        contact = _call("POST", f"/users/{uid}/contacts", {"name": CONTACT[0], "relation": CONTACT[1], "phone": CONTACT[2]})
        print(f"  + contact {CONTACT[0]} (made-up number)")
    for kind, label, value, names in todo:
        if kind == "whatsapp":
            value = str(contact["id"])  # type: ignore[index]
        _call("POST", f"/users/{uid}/app-links", {"kind": kind, "label": label, "value": value, "spoken_names": names})
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
