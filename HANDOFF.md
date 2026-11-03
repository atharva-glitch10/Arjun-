# HANDOFF (2026-11-03)

## Where we are
Item 4 is implemented and all suites are green. **Stop for review: nothing is committed or pushed.**
Part A (distress reply fix) and Part B (free family alerting: Telegram + LiveKit family call) are both in
the working tree as uncommitted edits.

## What changed
- **Part A (reasoning)**: `_safety` now uses `core.distress(...)["caregiver_alerted"]` and claims the family
  was told ONLY when it was. Family lookup is son → other family (never a doctor) → "तुमच्या घरच्यांना";
  the `contacts[0]` fallback is gone. The "आता कसं वाटतंय?" follow-up is removed from the symptom replies and
  the Evon prompt. `REQUEST_CAREGIVER` says "{family_obj} निरोप पाठवला आहे." (never "फोन लावला").
- **Part B (core-api)**: `telegram.py` sends alerts from a daemon thread (httpx, inline "Join call" button),
  deduped per (user, kind) for 10 minutes; `alert_sent` / `alert_failed` rows land in the family feed.
  `joins.py` signs 30-minute join links bound to the user id only; `family_call.py` (`GET /family/join?t=`)
  looks up the elder's room **when the link is redeemed** (not when the alert was sent) and exchanges it for a
  LiveKit token as identity `family`. `livekit_token.py` remembers the most recent room.
  Triggers: emergency (always), distress (consent only), `REQUEST_CAREGIVER` confirm. `POST
  /users/{id}/alert/test` is the manual check.
- **Part B (voice-agent)**: `familyroom.FamilyPresence` keeps Arjun quiet (no replies, no reminders, no
  idle close) while identity `family` is in the room.
- **Part B (web)**: `?view=join&t=...` renders `JoinCall` (mic on, big "बंद करा"); the elder page shows
  "… बोलत आहेत" and plays the family audio. With no open room the page says "आई सध्या ॲपवर नाहीत" and offers
  "पुन्हा प्रयत्न करा"; it never opens a LiveKit connection.
- `.env.example` documents `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `BASE_URL`,
  `JOIN_SECRET`; `scripts/dev-up.ps1` passes them to core-api; `scripts/telegram_test.py --call` queues a
  test alert with a join link for user 1.

## How to hand-test (not done in a browser)
1. Set `TELEGRAM_ENABLED=1` and the token/chat id in `.env`; start the stack (`scripts\dev-up.ps1`).
2. Open the elder page once (pre-warm) so core-api knows the room.
3. `python scripts/telegram_test.py --call` → a Telegram message with "📞 आईशी बोला / Join call".
4. Tap the button → the join page opens, mic on; the elder page shows "… बोलत आहेत"; Arjun does not speak.
5. Trigger a real emergency through the elder page and confirm the Telegram text + dashboard feed.

## Known limits (also in STATUS.md)
- The active-room map is in memory and points at the elder's **most recent** room. The join link is resolved at
  redemption, so a replaced room is followed; after a core-api restart the map is empty and the join page says
  "आई सध्या ॲपवर नाहीत" until the elder opens the app again.
- Dedupe state is in memory (one core-api process), reset by a restart.
- Telegram delivery is best effort; the dashboard alert is written first and never depends on it.

## Next step
Review the working tree. After approval: commit and push. Then Item 5 (whatever the roadmap says next).
