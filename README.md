# Arjun - voice care companion for elderly Indians (MVP)

Spec and hard boundaries: [CLAUDE.md](CLAUDE.md). Arjun is an AI, a bridge to people - not a
replacement for them. No medical advice, no emergency detection, stories private by default.

## What works today (verified by tests / smoke run)
Text/transcript in -> reasoning -> core-api (SQL) -> templated reply out, in Marathi / Hindi / English.

| Piece | State |
|---|---|
| `services/core-api` | FastAPI + SQLAlchemy. Reminders, appointments, contacts, **family-managed medicines + dose tracking (self-reported, family-only notice when unconfirmed)**, propose/confirm/reject actions, private stories + caregiver-visible Memory Book, distress events with consent gate, scheduler hook. 38 pytest tests (incl. API-key checks; core-api refuses to start without `CORE_API_KEY`). |
| `services/reasoning` | `POST /turn`: physical-emergency check, then distress check, first on every turn -> AI disclosure -> intent (rule-based parser; the hosted LLM only for chat and for turns the rules cannot read) -> dispatch. 281 pytest tests incl. distress and physical-emergency test sets (both lexicons unverified by a native speaker), core-api-outage handling, and dedicated medicine-path tests (intake with spoken yes, deflected medicine questions, no voice-created medicines). |
| `services/scheduler` | Polls core-api to mark due reminders, tick medicines, and fetch briefing/opener text. **Logs only: nothing is spoken on the elder device yet (T8).** 3 pytest tests. |
| `web/` | Vite + React + strict TS, rebuilt to the "Ghar" design in `design/` (tokens, toran/diya motifs, Devanagari elder screens, family dashboard). Elder home -> listen -> confirm -> saved is wired to reasoning `/turn` + core-api pending actions. `npm run build` passes; the screens were rendered in headless Edge (`/?preview` gallery, dashboard, elder home) but not tested on a real device or with real speech. |
| `eval/` | `python eval/run_eval.py` - intent / slot / distress on 33 synthetic text cases. |
| `services/voice-agent` | `agent.py` imports and its plugin arguments match livekit-plugins-gnani 1.8.6 (STT `mr-IN`, TTS, silero VAD, `StopResponse`). Verified 2026-10-21: the worker starts and registers with LiveKit Cloud. Gnani TTS returned audio through the plugin (2026-10-21). **No full spoken turn has run yet (T4).** The worker registers as `agent_name="arjun"`; `scripts/make_token.py` dispatches it explicitly. Reasoning failures become a spoken fallback line. 9 pytest tests (`test_bridge.py`, `test_turnlog.py`). Elder web app still uses **browser** speech, not Gnani (T6). |

## Run
```
cp .env.example .env            # set CORE_API_KEY; leave LLM_BASE_URL empty for rules-only mode
docker compose up --build       # postgres, core-api :8000, reasoning :8001, scheduler, web :5173
```
Local without Docker: `scripts\dev-up.ps1` starts core-api (SQLite), reasoning, voice-agent and web, in that order, one window
each (logs also go to `logs/`). It reads the one root `.env`, passes each service only the variables it needs and overrides the
compose-only hosts. `-Only <service>` starts one. The scheduler is not started by it. voice-agent loads only `GNANI_*` and
`LIVEKIT_*` from `.env` itself and exits naming any missing required variable. Tests: create a venv, `pip install -r services/core-api/requirements.txt -r services/reasoning/requirements.txt`,
then `pytest` inside each service and `ruff check .` at the root.

## Safety design in code
- LLM never writes to the DB. Reasoning proposes -> core-api validates and stores a *pending* action ->
  only a spoken yes (`CONFIRM_YES`) executes it.
- Reminders / appointments / contacts are answered from SQL only.
- Ambiguous AM/PM, missing date, or "after the meal" without which meal -> Arjun asks, never guesses.
- Distress: rule-based keyword net (recall-biased), overrides everything, rejects any pending action,
  mentions Elderline 14567 (8 AM-8 PM) and offers a family call. Caregiver is alerted only if
  `consent_distress_alert` is set, and no conversation text is stored or sent.
- Care-mode replies are fixed templates, so nothing medical or invented can be spoken.
- Stories: saved only after a spoken yes, private by default, shared only after a second spoken yes;
  `/memory-book` returns shared stories only; "he visar" deletes.

## Known limitations (honest list)
- **Parser quality is unmeasured.** The 42 eval cases were written alongside the parser, so 100% there
  says nothing about real speech. Needs real transcripts of elderly Marathi speakers.
- Task text is the leftover words after removing time/command words (e.g. "doctor jaycha"), not a clean noun phrase.
- **A pending yes/no is protected** (fix B, from the first hand test): while Arjun waits for an answer, anything that
  is not yes / no / cancel / a restated reminder gets the SAME question again; chat, a "keep your story?" offer or
  any other proposal can never replace it. A pending action expires after `PENDING_TTL_S` (default 300 s) in core-api.
  Runaway repetition from the recognizer ("हो हो हो कर कर कर ...") is collapsed on every turn. UNVERIFIED with a
  real voice after these fixes.
- The voice session serves the user id carried in the token's dispatch metadata (`ARJUN_USER_ID` is only the fallback
  for Console rooms). The dashboard refreshes every 10 s and on focus; "Create demo user" asks first. The demo uses
  ONE synthetic user (user 1): `python scripts/clean_demo_db.py` lists what would be removed (dry run), `--apply`
  does it after a backup.
- **Spoken clock hours** (एक..बारा, ek..barah, साडे/सव्वा/पावणे, दीड, अडीच) are read as times only next to a clock
  word ("दहा वाजता") or a day-part ("सकाळी दहा"); other spellings Prisma may produce are untested. If a clock word is
  heard with no readable hour, Arjun asks "किती वाजता?". A bare day-part with no clock word ("सकाळी") still means the
  family-set wake/meal time.
- **Open conversation needs the hosted LLM.** Without `LLM_BASE_URL` the companion rotates four fixed lines, so
  anything that is not a care command gets an off-topic answer (seen in the first real-speech test). With it set,
  only companion/chat replies and turns the rules cannot read go to the provider; care commands, times, medicines,
  confirmations and safety never do. See the next bullets for what is and is not verified.
- "उद्या काय आहे" reads tomorrow from SQL (medicines are computed from the family schedule, nothing is written). A
  sentence naming two days ("उद्या आज काय आहे") asks which day; the answer "उद्या" alone is not understood yet.
- A stale reply (the user spoke again first) is dropped only if it is a plain care or companion reply. Safety replies
  (emergency / distress) and any reply that asks a yes/no are always spoken, so a later "yes" never confirms an action
  the user did not hear. UNVERIFIED live.
- Gnani TTS: each spoken reply opens a new WebSocket (~0.9-1.2 s connect on this laptop, measured) before audio
  starts; see STATUS.md. Not changed yet.
- Only the first interest is used for openers; opener delivery to the voice session is not wired (scheduler logs it).
- Distress check is keyword + stem-pattern rules (spelling folded: anusvara/chandrabindu, i/u length, nukta) and
  now answers even if core-api is down. The lexicon is **unverified**: written without a native speaker or real
  Prisma output, and its tests were written by the same author, so they are not an independent recall measure.
  Not handled: loneliness phrases, falls, chest pain / physical emergencies (policy decision pending), and some
  everyday phrases ("sab khatam ho gaya" for milk) still trigger a check-in. Distress check was keywords only; Evon can additionally return `DISTRESS` but there is no separate classifier.
- Slot-filling drafts live in reasoning's memory (single instance; lost on restart).
- Single shared API key, no caregiver/elder role separation or login yet. The Memory Book endpoint is
  caregiver-safe by construction, but the elder-side `/stories/latest` is not protected from a caregiver
  holding the key. Do not expose beyond a demo.
- Timestamps are naive local time (IST); no timezone handling. Tables created with `create_all`; no Alembic migrations yet.
- **Do not publish Prisma/Timbre accuracy numbers yet.** Gnani's EULA clause 16 bars disclosing benchmark results
  outside your organization, and it is unknown whether it applies to the challenge API platform. Ask on the Gnani
  Discord first. Until then, report results for Arjun as a system (e.g. reminders completed correctly), not WER for
  Prisma. Also unanswered: credit cost per call, what happens when credits run out, and whether a teammate may use
  the primary registrant's key (credits and the key belong to the primary registrant).
- **The conversation LLM is a hosted, non-Gnani provider** (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`,
  `LLM_PROVIDER_NAME`; `EVON_*` still work as aliases; `LLM_SEND_TEMPLATE_KWARGS=0` for non-vLLM). Gnani = Prisma
  (hearing) + Timbre (voice); Evon is not used. **Whatever the elder says in an open-conversation turn is sent to
  that provider**, so the demo uses synthetic data only. CLAUDE.md open question 5 (is a non-Gnani LLM allowed in
  the entry?) is still unanswered on Discord: say plainly in the posts which model does what. No provider is
  configured yet, so nothing has run through it live. Reply quality in Marathi is unmeasured (`eval/llm_compare.py`
  measures it once a provider is set). Limits: one ~4 s budget per turn, 120 tokens, last four exchanges, no name
  or contact details sent; replies that claim to be human, say "I missed you", give medical advice, or recite
  recipes/facts are replaced by a fixed line.
- Companion conversation: the elder screen now keeps listening after a CHAT reply (ends on silence, "nako", or the
  back button), and reasoning sends the LLM the last four exchanges of this conversation plus the user's interests
  (in memory only, dropped after 30 min idle or on distress, never stored). Covered by mock-provider tests only:
  **no real LLM reply and no real speech has run through it**, so reply quality, Marathi fluency and the
  hands-free loop on a real device are unverified. Without `LLM_BASE_URL` the replies are still the 4 canned lines.
- Companion CHAT replies are rotating templates unless an LLM is configured. `COMPANION_TEMPERATURE=0.6`
  is Gnani's recommendation for Evon, **not yet chosen by our testing**. The client is only tested against a mock
  transport.

- **Medicines (new):** family creates/edits them on the dashboard; Arjun can only record "taken" / "snooze"
  after a spoken yes (or a tap) and deflects every medicine question to "ask the doctor". Verified by tests
  and one local end-to-end run (core-api + reasoning + web in headless Edge). Not verified: real speech, real
  device, the scheduler container, or delivery of the due-announcement to a voice session (the scheduler only
  logs it; the elder screen finds due doses by polling every 30 s and speaks them with browser TTS).
- Medicines are anchored to wake / lunch / dinner (+ family offset) or a fixed time; there is no
  "after breakfast" because no breakfast time exists yet. Snoozes are capped at the medicine's
  "ask up to" count. "On time" = within the medicine's window (default 30 min), all self-reported.
- Voice reminders that mention a medicine are refused on purpose (family sets medicine times); this also
  means a plain voice reminder like "tablet remind kar" now gets the "your family sets medicine times" reply.
- **Still not built:** BP / sugar readings, meal and walk check-ins, "Export for doctor", medicine-strip photo
  upload (the dashboard takes a link). The dashboard keeps "Not set up" for those; the BP screen exists in
  `web/src/ghar/Screens.tsx` (shown at `/?preview`) but is not wired.
- New tables (`medicines`, `medicine_doses`) are added by `create_all`; there are no migrations, and an
  existing database is not altered otherwise.
- The elder UI talks only through LiveKit + Gnani (T6): tap बोला -> `POST /livekit/token` (fresh room, explicit
  "arjun" dispatch) -> mic -> the screen mirrors the agent's `arjun.screen` attribute. No browser speech API is
  used anywhere (`scripts/check_no_browser_speech.py`, also a test). Verified without a browser by a LiveKit client
  script; **not yet verified in a real browser**. Browser echo cancellation + noise suppression are ON because the
  agent has no noise filter (open question 6).
- The elder page needs a secure origin for the microphone: `http://localhost` works; a phone needs HTTPS. Options,
  none set up yet: (1) Android + USB: `adb reverse tcp:5173 tcp:5173`, then open `http://localhost:5173` on the
  phone; (2) `vite --https` with a local certificate (mkcert) and the laptop's LAN address; (3) an HTTPS tunnel
  (cloudflared / ngrok) to port 5173, which also exposes the dev proxy and its API key, so demo data only;
  (4) Chrome's `unsafely-treat-insecure-origin-as-secure` flag on the phone, for a quick test only.
- Due-medicine prompts on the elder screen are **screen only** and say so ("not spoken") until T8.
- Honorific ("आजी") and the animation switch are not stored server-side: honorific is a constant, "turn off
  animations" is per-device (localStorage). Evening theme is chosen by clock (17:00-05:00) or `?theme=evening`.
- Design open questions still need testing with real elders: diya-only speak button, motion, script preference.

- **Clock and day guidance (new):** every service reads the household clock (`ARJUN_TZ`, default
  Asia/Kolkata) instead of the machine clock, so containers in UTC are not 5h30 off. `GET /users/{id}/day`
  is the single SQL-backed view of today (items, what is due now, what is next). Arjun answers "kiti vajle",
  "aaj konta divas" and "ata kay karaycha" from that clock + SQL through fixed templates, `/briefing/{id}`
  gives a once-a-day greeting + plan (the scheduler logs it; delivery to a voice session is not wired), and
  LLM prompts receive the current time. The elder screen shows the clock using server time (corrects a
  phone with a wrong clock). Verified by tests and a local run; not yet verified in a container.
- Time guidance only reads what the family set (reminders, appointments, medicines, wake/lunch/dinner
  times). It does not suggest activities. "Next" can be a meal time, which is a family-set marker, not a
  confirmed meal. Day boundaries are midnight in the household timezone; no DST handling is needed for IST.

## Deferred (per CLAUDE.md "stretch" / not started)
pgvector RAG over stories and past-story recall, RSS topic news, S3 TTS cache, MongoDB trace logging
(per-stage timings are only logged to stdout), nginx 2-replica load balancing, noise-cancellation A/B,
WER and latency measurement.

## Open questions (need a human / credentials - not guessed)
Prisma streaming support for the target language; credit cost per Gnani call; whether noise
cancellation helps or hurts Prisma; whether LiveKit turn-detection can change mid-session (the
1.0s / 3.0s endpointing values (`ARJUN_MIN/MAX_ENDPOINTING_S`) are placeholders); which embedding model
works for the target language. Target language was assumed to be Marathi from the spec's examples.
