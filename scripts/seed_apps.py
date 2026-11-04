"""Seed the synthetic demo household (user 1) with the apps she can open by voice. DRY RUN unless --apply.

  python scripts/seed_apps.py                 # verify the links, print what would be added, change nothing
  python scripts/seed_apps.py --apply         # add the missing entries (safe to run twice: existing labels are kept)
  python scripts/seed_apps.py --user 2 --apply

Every URL is checked against the public web BEFORE anything is written: HTTP 200, and the playlist / channel id is
really on its YouTube page. Anything that fails is left out and named, never guessed. The script goes through
core-api, so every value is validated like a family entry; it never touches a database file. CORE_API_URL and
CORE_API_KEY come from the environment or the root .env, and the key is never printed.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONTACT = ("चंद्रकांत", "मुलगा", "00000 00003")  # made up, not a real number
USER_AGENT = "Mozilla/5.0 (compatible; arjun-seed/1.0; +local demo)"
UNREACHABLE = ("does not exist", "isn't available", "is not available", "this video isn't available")

# (kind, label, value, spoken names). value for "whatsapp" is filled in with the contact id at apply time.
LINKS: list[tuple[str, str, str, list[str]]] = [
    # Public Marathi bhakti-geete playlist "Super Hit Pahateche Bhakti | Prabhat Geet" (Wings Marathi Bhakti).
    ("youtube_playlist", "भक्तिगीते", "PL01mceoBxHCiCj28l-viryuhBh7nXsqZN", ["भजन", "भक्तिगीते", "अभंग"]),
    # ABP MAJHA (Marathi news) live channel.
    ("youtube_channel_live", "बातम्या", "UCH7nv1A9xIrAifZJNvt7cgA", ["बातम्या", "न्यूज"]),
    ("rss", "एबीपी माझा", "https://marathi.abplive.com/home/feed", ["एबीपी माझा"]),
    ("rss", "बीबीसी मराठी", "https://feeds.bbci.co.uk/marathi/rss.xml", ["बीबीसी मराठी"]),
    ("whatsapp", "चंद्रकांत", "", ["चंद्रकांत"]),
    # Phone apps (the elder page builds the link itself; one tap opens the app).
    ("app", "स्पॉटिफाय", "spotify", ["स्पॉटिफाय", "spotify"]),
    ("app", "जिओसावन", "jiosaavn", ["जिओसावन", "सावन"]),
    ("app", "यूट्यूब म्युझिक", "youtube_music", ["यूट्यूब म्युझिक"]),
    ("app", "गूगल मॅप्स", "google_maps", ["मॅप्स", "नकाशा"]),
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


def _fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - public demo pages, https only
        return r.status, r.read(3_000_000).decode("utf-8", "replace")


def verify(kind: str, value: str) -> tuple[bool, str]:
    """(True, proof) when the entry really exists; (False, reason) when it must be left out. Never guesses an id."""
    if kind == "app":
        return True, "phone app (no URL stored)"
    if kind == "whatsapp":
        return True, "no URL; the contact is checked against core-api"
    if kind == "youtube_playlist":
        url = f"https://www.youtube.com/playlist?list={urllib.parse.quote(value)}"
    elif kind == "youtube_channel_live":
        url = f"https://www.youtube.com/channel/{urllib.parse.quote(value)}"
    else:
        url = value
    try:
        status, body = _fetch(url)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, f"could not fetch ({exc})"
    if status != 200:
        return False, f"HTTP {status}"
    low = body.lower()
    if kind.startswith("youtube_"):
        if value not in body:
            return False, "HTTP 200 but the id is not on the page"
        if any(marker in low for marker in UNREACHABLE):
            return False, "YouTube says it is not available"
        return True, f"HTTP 200; {'playlist' if kind == 'youtube_playlist' else 'channel'} {value} exists"
    if not body.strip():
        return False, "HTTP 200 but the page is empty"
    return True, "HTTP 200"


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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Marathi labels print on a Windows console too
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the entries (default: dry run)")
    ap.add_argument("--user", type=int, default=1)
    args = ap.parse_args()
    _load_env()
    uid = args.user

    print(f"seed_apps: user {uid}, {'APPLY' if args.apply else 'dry run (nothing is written)'}")
    print("verifying every link before writing:")
    verified: list[tuple[str, str, str, list[str]]] = []
    failed = 0
    for kind, label, value, names in LINKS:
        ok, detail = verify(kind, value)
        mark = "OK  " if ok else "SKIP"
        shown = value or f"(contact {CONTACT[0]})"
        print(f"  {mark} {kind:22} {label:14} {shown}  {detail}")
        if ok:
            verified.append((kind, label, value, names))
        else:
            failed += 1
    print(f"verified {len(verified)} of {len(LINKS)} entries; {failed} left out (verification failed)")

    try:
        contacts = _call("GET", f"/users/{uid}/contacts")
        have = {(link["kind"], link["label"]) for link in _call("GET", f"/users/{uid}/app-links")}
    except (urllib.error.URLError, OSError) as exc:
        print(f"core-api is not reachable ({exc}). Start it first (scripts/dev-up.ps1).")
        return 1

    contact = next((c for c in contacts if c["name"] == CONTACT[0]), None)
    todo = [(k, label, v, names) for k, label, v, names in verified if (k, label) not in have]
    if contact is None and any(k == "whatsapp" for k, *_ in todo):
        print(f"  contact {CONTACT[0]}: missing" + ("" if args.apply else " (would be created on --apply)"))
    elif contact is not None:
        print(f"  contact {CONTACT[0]}: id {contact['id']}")

    if not todo:
        print("nothing to add: every verified entry is already there (idempotent).")
        return 0
    print(f"{len(todo)} entr{'y' if len(todo) == 1 else 'ies'} to add" + ("" if args.apply else " (dry run)"))
    for kind, label, value, _ in todo:
        print(f"  + {kind:22} {label}  {value or '(the contact ' + CONTACT[0] + ')'}")
    if not args.apply:
        return 0

    if any(k == "whatsapp" for k, *_ in todo) and contact is None:
        contact = _call(
            "POST", f"/users/{uid}/contacts", {"name": CONTACT[0], "relation": CONTACT[1], "phone": CONTACT[2]}
        )
        print(f"  + contact {CONTACT[0]} (made-up number) id {contact['id']}")
    for kind, label, value, names in todo:
        if kind == "whatsapp":
            value = str(contact["id"])  # type: ignore[index]
        row = _call(
            "POST", f"/users/{uid}/app-links", {"kind": kind, "label": label, "value": value, "spoken_names": names}
        )
        print(f"  added {kind:22} {label}  id={row['id']} value={row['value']}")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
