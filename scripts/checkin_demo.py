"""Live demo of the proactive day check-ins.

Usage:
  python scripts/checkin_demo.py --user 1 --now 09:30           print today's plan, then ask the next check-in NOW
  python scripts/checkin_demo.py --user 1 --now 09:30 --setup   first switch check-ins on and open the window 07:00-21:00
  python scripts/checkin_demo.py --user 1 --plan-only           only print the plan and the day card

`--now HH:MM` is the time of day the demo pretends it is: it is checked against her opener window and the quiet
hours (22:00-06:30) exactly like a real tick. The prompt itself is queued at the real time, so the open elder
page (voice session) speaks it within a few seconds. The daily cap and the 30-minute gap are not applied, so the
demo can be repeated.

Needs core-api running with ARJUN_CHECKIN_DEMO=1 (otherwise the fire step answers 404; the plan still prints).
The API key is read from .env and never printed. Only synthetic data; no phone numbers are read or printed.
"""

import argparse
import os
import sys

import httpx
from dotenv import dotenv_values

LABEL = {
    "sleep": "सकाळ (झोप)", "breakfast": "नाश्ता", "lunch": "जेवण", "walk": "फिरणं", "interest": "आवड",
    "home": "घर", "dinner": "संध्याकाळ (रात्रीचं जेवण)", "bp": "बीपी", "appointment": "भेट", "reminder": "काम",
    "medicine": "औषध",
}
MARK = {"done": "OK", "not_done": "NO", "no_answer": "--", "waiting": "..", "not_asked": "  "}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", type=int, default=1)
    ap.add_argument("--now", help="HH:MM the demo pretends it is (needed to fire)")
    ap.add_argument("--setup", action="store_true", help="switch check-ins on and open the window to 07:00-21:00")
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()
    if not args.plan_only and not args.now:
        ap.error("give --now HH:MM (or --plan-only)")

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    env = dotenv_values(".env")
    key = (os.environ.get("CORE_API_KEY") or env.get("CORE_API_KEY") or "").strip()
    base = (os.environ.get("CORE_API_URL") or env.get("CORE_API_URL") or "http://127.0.0.1:8000").rstrip("/")
    http = httpx.Client(base_url=base, headers={"X-API-Key": key} if key else {}, timeout=10)

    def call(method: str, path: str, **kw):  # type: ignore[no-untyped-def]
        try:
            return http.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise SystemExit(f"core-api is not reachable at {base}: {type(exc).__name__}") from exc

    user = call("GET", f"/users/{args.user}")
    if user.status_code != 200:
        raise SystemExit(f"user {args.user}: HTTP {user.status_code}")
    u = user.json()

    if args.setup:
        patch = {"daily_checkins": True, "opener_start": "07:00", "opener_end": "21:00"}
        changed = {k: (u[k], v) for k, v in patch.items() if u.get(k) != v}
        if changed:
            res = call("PATCH", f"/users/{args.user}", json=patch)
            if res.status_code != 200:
                raise SystemExit(f"setup failed: HTTP {res.status_code}")
            for k, (old, new) in changed.items():
                print(f"setup: {k}: {old} -> {new}")
            u = res.json()
        else:
            print("setup: nothing to change")

    print(
        f"\n{u['name']}: wake {u['wake_time']}, lunch {u['lunch_time']}, dinner {u['dinner_time']}, "
        f"window {u['opener_start']}-{u['opener_end']}, check-ins {'ON' if u['daily_checkins'] else 'OFF'}"
    )
    if not u["daily_checkins"]:
        print("Check-ins are OFF for this person (the family switch). Add --setup to turn them on for the demo.")
        return 1

    plan = call("GET", f"/users/{args.user}/checkins")
    plan.raise_for_status()
    print("\nToday's plan (generated from her own data):")
    print(f"  {'time':5}  {'kind':14} {'about':28} status")
    for c in plan.json():
        about = c["ref"].replace("|", " - ") if c["ref"] else ""
        print(f"  {c['due_at'][11:16]}  {c['kind']:14} {about[:28]:28} {c['status']}")

    if not args.plan_only:
        res = call("POST", f"/users/{args.user}/checkins/demo-fire", json={"now": args.now})
        if res.status_code == 404:
            print("\nThe demo switch is off. Set ARJUN_CHECKIN_DEMO=1 in .env, restart core-api, and run this again.")
            return 2
        res.raise_for_status()
        out = res.json()
        if out["fired"]:
            about = f" ({out['ref'].replace('|', ' - ')})" if out.get("ref") else ""
            print(f"\nASKED NOW: {out['fired']}{about}. Open the elder page; Arjun speaks it within a few seconds.")
        else:
            print(f"\nNothing asked: {out['reason']}")

    card = call("GET", f"/users/{args.user}/checkins/card")
    if card.status_code == 200:
        print("\nFamily card 'आजचा दिवस' (OK done, NO not done, -- no answer, .. waiting):")
        for i in card.json():
            name = LABEL.get(i["kind"], i["kind"])
            extra = f" ({i['label']})" if i["label"] else ""
            print(f"  {MARK.get(i['state'], '??')}  {i['at'][11:16]}  {name}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
