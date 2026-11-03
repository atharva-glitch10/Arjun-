# HANDOFF (2026-11-03, proactive day check-ins)

## Where we are
Proactive day check-ins are implemented and tested. **Media work (Tasks 1-3) was not touched.** Nothing is pushed.
The working tree also still holds the earlier uncommitted work (Telegram/family call and the media WIP).
**Not committed**: the reasoning suite is red only because of the on-hold media tests (see below), and the brief said
commit only when everything is green.

## What changed (details in STATUS.md)
- core-api: `checkin_plan.py` (new), `checkins.py` (rules, postpone, volunteer, day card, demo-fire), `models.py` /
  `db.py` / `schemas.py` (columns ref, postponed, mood, source), `deliveries.py` (`detail` = what the question is about).
- reasoning: `checkins.py` (answers per topic, volunteered topics), `turn.py` (prompts from SQL, safety-first answers,
  busy -> postpone, family offer, interest -> media flow), `evon.py` (`checkin_understanding`), `replies.py`,
  `core_client.py`, `main.py` (`media_playing`).
- voice-agent: sends `media_playing` with every delivery claim (`bridge.py`, `agent.py`).
- web: `family/daycard.ts` (+ test), the "आजचा दिवस" card in `Dashboard.tsx`, `api.ts`.
- `scripts/checkin_demo.py`, `.env.example`, `scripts/dev-up.ps1` (passes the three new variables).

## Red items that are NOT from this task
- `services/reasoning/tests/test_app_commands.py`: 8 failures (11 on a clean `git archive HEAD`) in the media area.
- `ruff`: `understand_media` unused + import order in `reasoning_svc/turn.py` (left by the media WIP).
Fix those first if you want a one-shot commit. My files: everything above except the Telegram/media leftovers;
`turn.py` mixes my hunks with the media WIP, so use `git add -p` there.

## Decisions you may want to change
1. Medicine is not a second question and "आत्ता घ्या" is not said (boundary 6). Say so if you want it anyway.
2. The opener window applies literally. User 1 (09:00-19:00): sleep (07:30) and breakfast (08:30) are asked when the
   window opens at 09:00 if under 90 min old; dinner (20:30) is never asked. Widen the window on the dashboard
   (or `--setup`) to 07:00-21:00 to see all of them.
3. The snack check-in is no longer scheduled.

## Phone test (about 10 minutes)
1. In `.env` set `ARJUN_CHECKIN_DEMO=1` (and leave `ARJUN_CHECKINS_ENABLED=1`). Start the stack: `scripts\dev-up.ps1 -Phone`.
2. Open the elder page on the phone, tap to start, let Arjun finish the greeting, and stay quiet for 2 minutes.
3. `.venv\Scripts\python scripts\checkin_demo.py --user 1 --now 09:30 --setup`
   (prints the plan, switches check-ins on + window 07:00-21:00 for user 1, asks the next one). Within ~5 s Arjun says
   "नमस्कार Demo Aaji, रात्री झोप नीट लागली का?" (the honorific is used when set).
4. Answer "हो, छान लागली" -> expect "बरं झालं." Run the script again with `--now 10:30` -> the next question.
   Try: "नाही" to a meal (expect the one-line nudge), "पोट दुखतंय" to a question (symptom flow, not "skipped"),
   "हो" to the भजन question (media flow), "नाही" to the family question then "हो" (a Telegram message and undo).
5. While a video plays, run the script: the question must NOT be spoken; it comes back 10 minutes later.
6. Open the dashboard: the "आजचा दिवस" card shows ✅/❌/— with times. `--plan-only` reprints it.
7. Set `ARJUN_CHECKIN_DEMO=0` again afterwards.
