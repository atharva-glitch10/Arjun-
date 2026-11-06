# Modules

Line counts are from the working tree (non-test files). "Depended on by" uses Graphify's file-level import and call edges (non-test files) plus the code I read. The most-connected graph nodes are `TurnEngine.handle` (162 edges), `TurnEngine` (145), `CoreClient` (105), `core_api/main.py` (96) and `Dashboard.tsx` (88).

## services/core-api (source of truth, SQL)

| File | Lines | What it does | Depended on by |
|---|---|---|---|
| `main.py` | 767 | App assembly; users, contacts, reminders, appointments, stories, the propose/confirm/undo/reject action flow, distress/emergency, help requests, fire-due. Mounts 13 routers. | uvicorn; tests; `scripts/clean_demo_db.py` |
| `models.py`, `db.py` | 338, 74 | 20 SQLAlchemy tables; engine; hand-rolled "add missing column" step (no migrations). | every router (`models` has 16 importing files, `db` 15) |
| `deps.py` | 57 | `require_key`, `get_now`, timezone, `check_api_key_configured`. | 14 files |
| `schemas.py` | 353 | Pydantic in/out models. | main, medicines, checkins, day, readings |
| `medicines.py` | 328 | Family-only medicine CRUD, dose rows, tick, taken/snooze. | main (router), tests |
| `checkins.py`, `checkin_plan.py` | 480, 109 | Daily check-in planning, asks, follow-ups, postpone, day card. | main, scheduler (via HTTP) |
| `deliveries.py` | 339 | Queue of things to speak: enqueue, claim, spoken, release, ack, sweep. | main, medicines, checkins, reasoning (via HTTP) |
| `feed.py` | 201 | `before_flush` hook turns Notification/Wellbeing into FeedEvent; WS broker; REST fallback. | main; dashboard |
| `wellbeing.py` | 102 | Per-conversation mood/level rows. | main, reasoning (HTTP) |
| `telegram.py` | 220 | Telegram alerts on a daemon thread, 10-minute dedupe, outcome rows. | main |
| `livekit_token.py` | 94 | Elder JWT + agent dispatch; in-memory `_rooms`. | main, `family_call.py`, web |
| `family_call.py`, `joins.py` | 101, 56 | Signed join link and family JWT. | main, telegram path |
| `media.py` | 280 | YouTube search with cache and daily quota; RSS headlines. | main, reasoning (HTTP) |
| `applinks.py` | 251 | Family-approved links (YouTube, RSS, WhatsApp) with URL validation. | main, media |
| `day.py`, `activity.py`, `readings.py`, `recurrence.py`, `ratelimit.py` | 142, 66, 109, 44, 69 | Day card, last-seen, BP and watch samples (frozen scope), weekly rules, per-IP rate limit. | main |

## services/reasoning (the brain; never touches the DB directly)

| File | Lines | What it does | Depended on by |
|---|---|---|---|
| `turn.py` | 2204 | `TurnEngine`: the whole turn pipeline, media cards, check-in answers, deliveries, briefing, medicine, companion. | `main.py`, tests, `eval/` |
| `main.py` | 232 | FastAPI endpoints `/turn`, `/delivery/*`, `/media/gate`, `/briefing`, `/opener`, `/conversations/flush-idle`. | uvicorn, voice-agent, scheduler |
| `distress.py` | 436 | Emergency and distress rules (lexicons, unverified). | turn, main (`/media/gate`), tests |
| `parser.py` | 552 | Rule-based intent and Marathi time grammar (the LLM fallback). | turn |
| `evon.py` | 807 | `EvonClient`: hosted LLM client (Sarvam or OpenAI-compatible), limiter, understanding, companion, summary. The "Evon" name is legacy. | turn, main, `eval/llm_compare.py` |
| `replies.py` | 724 | Fixed reply templates per language. | turn, app_replies |
| `core_client.py` | 176 | HTTP client to core-api (40 methods). | turn, wellbeing, checkins |
| `appcmd.py`, `app_replies.py`, `media_understanding.py` | 318, 115, 97 | App/media command parsing and wording. | turn (`media_understanding` is reached through `evon.py` by `hasattr`) |
| `wellbeing.py`, `checkins.py`, `readings.py`, `textutil.py`, `config.py`, `clock.py`, `ratelimit.py` | 174, 131, 47, 82, 125, 21, 25 | Conversation tracker, check-in wording, BP parse, text helpers, env config, clock, token bucket. | turn, main |

## services/voice-agent (LiveKit worker, `agent_name="arjun"`)

| File | Lines | What it does | Depended on by |
|---|---|---|---|
| `agent.py` | 444 | Entrypoint; wires STT/TTS, events, delivery loop, idle closer. | LiveKit CLI |
| `bridge.py` | 179 | HTTP to reasoning with a spoken fallback. | agent, responder, delivery |
| `responder.py`, `delivery.py` | 85, 80 | Speak one turn; pull and speak queued items. | agent |
| `media.py`, `mediamode.py`, `safety_words.py` | 106, 86, 193 | Hold off while a video plays; local copy of the safety words. | agent |
| `screenstate.py`, `sessionstate.py`, `familyroom.py`, `idle.py`, `endpointing.py` | 72, 36, 32, 91, 125 | Participant attributes; session flags; family presence; idle close; end-of-speech hold. | agent |
| `voice.py`, `voiceprovider.py`, `ttsgate.py`, `audiowarm.py`, `turnlog.py`, `applog.py`, `usermeta.py` | 52, 46, 38, 32, 213, 42, 20 | Model and voice choice; Sarvam test switch; one-at-a-time TTS; timing log. | agent |

## services/scheduler
`scheduler.py` (111): every 30 s, calls core-api `/internal/*` ticks and reasoning flush/briefing/opener. Keeps `_opened_today` and `_briefed_today` in memory.

## web (React + TypeScript + Vite)

| File | Lines | What it does |
|---|---|---|
| `main.tsx` | 73 | Picks the view from the URL (`elder`, `family`, `join`, gallery). |
| `api.ts` | 326 | All typed calls to `/core/*` (11 importing files). |
| `elder/ElderApp.tsx` | 635 | Big-button elder screen; cards; reminders. |
| `voice/useArjunVoice.ts`, `voice/state.ts`, `voice/action.ts` | 391, 132, 130 | LiveKit connection, attributes, media reducer. |
| `elder/MediaScreen.tsx`, `elder/media.ts`, `elder/useAppActions.ts` | 218, 156, 105 | YouTube player, plan an action, act on it. |
| `family/Dashboard.tsx` | 1155 | Whole dashboard in one component (13 imports). |
| `family/feed.ts`, `emergencyWatch.ts`, `alarm.ts`, `polling.ts`, `JoinCall.tsx` and small helpers | 154, 71, 116, 41, 157 | Live feed, emergency banner and sound, polling, family call page. |
| `ghar/Screens.tsx`, `Motifs.tsx`, `Gallery.tsx` | 743, 163, 117 | Design-system screens and a preview gallery. |

## Other
- `shared/schemas/intent.json` (23 inbound edges in the graph), `tool_calls.json` (no inbound edge): the contract between the LLM and the code.
- `scripts/*`: dev-up, token, seeding, eval, Telegram and tunnel helpers. Entry points by hand, so Graphify shows them as unreferenced.
- `eval/run_eval.py`, `eval/llm_compare.py`: offline evaluation, import from `reasoning_svc`.
- `docker-compose.yml`: Postgres (pgvector), core-api, reasoning, scheduler, web. **No voice-agent service.**
