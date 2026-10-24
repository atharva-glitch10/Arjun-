# Arjun — Project Overview

> A voice care companion for elderly Indians (Marathi / Hindi / English).
> Arjun is an AI and a bridge to people, not a replacement for them.
> It gives no medical advice and keeps stories private by default. A rule-based physical-emergency
> check (unverified lexicon) tells the user to call 112; it does not detect emergencies by itself.
>
> **Partly stale (last full update 2026-10-18).** README.md and STATUS.md are current.

This document describes what is implemented, how the tech stack is used, and what is still open.
For run instructions and the short status table, see [README.md](README.md).

---

## Table of contents

1. [What it does](#what-it-does)
2. [Architecture](#architecture)
3. [Components](#components)
4. [Turn pipeline](#turn-pipeline)
5. [Tech stack and how it is used](#tech-stack-and-how-it-is-used)
6. [Safety and privacy design](#safety-and-privacy-design)
7. [Testing and evaluation](#testing-and-evaluation)
8. [Running it](#running-it)
9. [Repository layout](#repository-layout)
10. [Known gaps and loose ends](#known-gaps-and-loose-ends)

---

## What it does

Text or a transcript goes in, and a templated reply comes out, in Marathi, Hindi or English.

| Capability | Summary |
|---|---|
| Reminders | Create, list today's, mark done. Asks for missing task, date or AM/PM instead of guessing. |
| Appointments | "When is my next appointment?" is answered from SQL. |
| Family calls | Nudges the user to call a saved contact. |
| Caregiver requests | "I need help" notifies the caregiver, after a spoken yes. |
| Stories | Saved only after a spoken yes, private by default, shared only after a second spoken yes, deleted on "he visar". |
| Distress handling | Checked on every turn. Overrides everything, points to Elderline 14567, and alerts the caregiver only with consent. |
| Proactive openers | At most one conversation opener per day, inside caregiver-set hours, skipped if the user declined. |
| Caregiver dashboard | Care settings, reminders, appointments, contacts, the Memory Book, requests and alerts. |

---

## Architecture

```
 Browser (React SPA)
   │  elder page: livekit-client -> LiveKit room -> voice-agent (Gnani Prisma + Timbre)
   │  caregiver dashboard
   │
   ├── /reasoning ──────────▶ reasoning  (FastAPI :8001)
   │                            ├─ distress rules  (first, every turn)
   │                            ├─ Evon LLM (optional) → schema-validated JSON
   │                            ├─ rule-based parser (fallback / confirmations)
   │                            └─ templated replies
   │                                   │ HTTP (propose / read)
   └── /core (API key injected) ──────▶ core-api  (FastAPI :8000) ──▶ Postgres
                                          ▲
        scheduler (poll loop) ────────────┘  fires due reminders, requests openers

        voice-agent (LiveKit + Gnani STT/TTS) ──▶ reasoning /turn   [unverified skeleton]
```

**Core idea: the LLM is boxed in.**
Reasoning can only *propose*. core-api validates every proposal and stores it as pending.
Only a spoken "yes" executes it. Care-mode replies are fixed templates, so nothing medical or invented can be spoken.

---

## Components

### `services/core-api` — source of truth
FastAPI + SQLAlchemy 2 + Pydantic v2.

- **Models:** `User`, `Contact`, `Reminder`, `Appointment`, `StoryMemory`, `PendingAction`, `CaregiverRequest`, `Notification`, `DistressEvent`, `TopicDecline`.
- **Propose → confirm / reject:** five action types are supported: `CREATE_REMINDER`, `COMPLETE_REMINDER`, `REQUEST_CAREGIVER`, `SHARE_STORY`, `SAVE_STORY`. A new proposal supersedes older pending ones.
- **Validation:** ambiguous AM/PM and past times are rejected with 422. HH:MM and language values are checked by Pydantic.
- **Scheduler hook:** `POST /internal/reminders/fire-due` marks due reminders as fired and writes a notification.
- **Opener gate:** `GET /users/{id}/opener-allowed` checks caregiver hours, daily decline and interests.
- **Auth:** shared `X-API-Key` header.
- **DB:** Postgres (psycopg 3) in Docker, SQLite fallback locally. Tables are created with `create_all`.

### `services/reasoning` — turn engine
FastAPI + httpx + jsonschema.

| File | Responsibility |
|---|---|
| `turn.py` | Orchestrates a turn and dispatches intents. |
| `distress.py` | Recall-biased keyword net in mr / hi / en (Devanagari and roman). |
| `parser.py` | Rule-based intent and slot extraction, with draft slot-filling across turns. |
| `evon.py` | OpenAI-compatible client for self-hosted Evon, with JSON-schema validation and one retry. |
| `replies.py` | Fixed templates in mr / hi / en and rotating companion prompts. |
| `core_client.py` | Thin HTTP client for core-api. |
| `textutil.py` | Normalisation, Devanagari digits, whole-token matching, language detection. |
| `config.py` | Fixed temperatures and env config. |

Endpoints: `POST /turn`, `POST /opener/{user_id}`, `GET /health`.

### `services/scheduler`
A polling loop (default 30 s). It fires due reminders through core-api and optionally asks reasoning for one opener per user per day.
Opener delivery is currently log-only.

### `web/` — React SPA
Vite 5 + React 18 + strict TypeScript.

- **Elder view:** one large talk button; it joins a LiveKit room and mirrors the agent (listening / confirm / saved / safety). Speech is Gnani only, no browser speech APIs. Always shows "Arjun is an AI assistant".
- **Caregiver dashboard:** reads and edits everything above, including the distress-alert consent checkbox. Uses `/memory-book` only, never `/stories`.
- **Dev proxy:** `/core` is proxied by Vite, and the API key is injected there so it never ships in the bundle. The browser no longer reaches reasoning at all.

### `services/voice-agent` — LiveKit + Gnani
- `bridge.py`: HTTP bridge to `/turn`, with placeholder endpointing delays (0.7 s care, 1.2 s companion).
- `agent.py`: **unverified skeleton**, never run (needs Gnani and LiveKit credentials and a check against the plugin API).

### `shared/schemas`
- `intent.json`: contract for LLM intent output (14 intents, date/time patterns, confidence, language).
- `tool_calls.json`: contract for proposed actions.

### `eval/`
`run_eval.py` + `cases.jsonl` (33 synthetic cases): intent accuracy, slot accuracy and distress recall.

---

## Turn pipeline

Order is fixed in `turn.py`:

1. **Distress check:** every turn, rules only, overrides everything. Rejects any pending action so a stray "yes" executes nothing.
2. **AI disclosure:** "are you human?" gets a fixed answer.
3. **Intent:**
   - Open reminder draft → short answers fill the slots.
   - Evon configured → schema-validated JSON at temperature 0, one retry, then fall back.
   - Otherwise → rule-based parser.
   - Confirm / decline / forget always come from the deterministic parser.
4. **Dispatch:** care intents are answered from SQL via core-api. Anything that writes is proposed, then confirmed by a spoken yes.
5. **Companion chat:** Evon at temperature 0.6 if configured, with a script and length check. Otherwise rotating "tell me more" templates.

---

## Tech stack and how it is used

| Technology | Where | How it is used |
|---|---|---|
| **FastAPI / Uvicorn** | core-api, reasoning | HTTP services. Dependency injection (`get_db`, `get_now`, `require_key`) keeps tests deterministic. |
| **SQLAlchemy 2** | core-api | Typed `Mapped[]` models. JSON columns for interests and action payloads. |
| **PostgreSQL (pgvector image)** | docker-compose | Primary store. The pgvector image is chosen for future RAG, not yet used. |
| **Pydantic v2** | core-api, reasoning | Request/response validation and field constraints. |
| **httpx** | all Python services | Service-to-service calls and Evon calls. Mock transports in tests. |
| **jsonschema** | reasoning | Validates LLM output against `shared/schemas/intent.json` before it is trusted. |
| **Gnani Evon** | reasoning | Optional intent extractor and companion chat via an OpenAI-compatible endpoint. Cannot write to the DB. |
| **Gnani Prisma / Timbre + LiveKit** | voice-agent | Real-time STT/TTS. Skeleton only. |
| **React 18 + Vite 5 + TypeScript** | web | Elder and caregiver UIs in one SPA. |
| **Docker Compose** | root | postgres, core-api, reasoning, scheduler, web. |
| **pytest / ruff** | all Python | 59 tests plus lint (E, F, I, B). |

---

## Safety and privacy design

- **LLM never writes to the DB.** Reasoning proposes → core-api validates and stores pending → only a spoken yes executes.
- **Facts from SQL only.** Reminders, appointments and contacts are never model-generated.
- **No guessing.** Ambiguous AM/PM, missing date, or "after the meal" without a meal means Arjun asks.
- **Templated care replies.** Nothing medical or invented can be spoken.
- **Distress overrides everything.** Rule-based, recall-biased. It offers a family call and mentions Elderline 14567 (8 AM–8 PM).
- **Consent-gated alerts.** The caregiver is alerted only if `consent_distress_alert` is set. No conversation text is stored or sent.
- **Stories are private by default.** The caregiver sees only explicitly shared stories via `/memory-book`.
- **Fixed temperatures.** Extraction is always 0.0. Companion 0.6 is Gnani's recommendation and is not yet chosen by our own testing.
- **Honest AI identity.** Arjun never claims to be human or to have feelings.

---

## Testing and evaluation

| Suite | Count | Notes |
|---|---|---|
| `services/core-api/tests` | 17 | SQLite in-memory, injected clock. |
| `services/reasoning/tests` | 42 | Includes a distress test set. Core and Evon are mocked. |
| `eval/run_eval.py` | 33 cases | Text-only. Intent, slots, distress recall. WER and latency are not measured. |

These counts come from the README and the test file sizes. Run the suites to confirm them.

**Caveat:** the eval cases were written alongside the parser, so a high score is a regression check, not a quality benchmark.

---

## Running it

```bash
cp .env.example .env          # set CORE_API_KEY; leave EVON_BASE_URL empty for rule-based mode
docker compose up --build     # postgres, core-api :8000, reasoning :8001, scheduler, web :5173
```

Without Docker:

```bash
python -m venv .venv
pip install -r services/core-api/requirements.txt -r services/reasoning/requirements.txt
pytest                         # run inside each service directory
ruff check .                   # at repo root
python eval/run_eval.py
```

### Environment variables

| Variable | Used by | Purpose |
|---|---|---|
| `CORE_API_KEY` | all | Shared API key. |
| `DATABASE_URL` | core-api | Postgres URL (SQLite fallback if unset). |
| `EVON_BASE_URL` / `EVON_MODEL` | reasoning | Self-hosted Evon. Empty means rule-based mode. |
| `OPENER_USER_IDS` | scheduler | Users who receive daily openers. |
| `GNANI_API_KEY`, `LIVEKIT_*` | voice-agent | Voice credentials. |
| `MONGO_URL` | none | Listed in `.env.example` but unused. |

---

## Repository layout

```
.
├── docker-compose.yml
├── .env.example
├── ruff.toml
├── README.md
├── eval/                      run_eval.py, cases.jsonl
├── shared/schemas/            intent.json, tool_calls.json
├── services/
│   ├── core-api/              core_api/{main,models,schemas,db}.py, tests/
│   ├── reasoning/             reasoning_svc/{turn,parser,distress,evon,replies,...}.py, tests/
│   ├── scheduler/             scheduler.py
│   └── voice-agent/           agent.py (unverified), bridge.py
└── web/                       src/{main,Elder,Dashboard,api}.ts(x), vite.config.ts
```

---

## Known gaps and loose ends

**Not verified**
- The voice agent has never run. Evon has never been called live (mock only). The web UI is type-checked but not exercised in a browser. The scheduler has no tests.

**Security (do not expose beyond a demo)**
- One shared API key, no login or roles.
- `/stories/latest` is reachable by anyone holding the key.
- The web Dockerfile runs the Vite dev server.

**Robustness**
- Slot-filling drafts and chat counters live in process memory, so they are lost on restart and break with multiple replicas.
- Timestamps are naive local time (IST). There are no Alembic migrations.

**Quality**
- Parser accuracy on real elderly speech is unmeasured.
- Reminder task text is leftover words (e.g. "doctor jaycha"), not a clean phrase.
- Only the first interest is used for openers. Opener delivery is not wired to the voice session.
- `PATCH /users/{id}` cannot clear a field to null.

**Deferred**
- pgvector RAG and past-story recall, RSS topic news, S3 TTS cache, MongoDB trace logging, nginx 2-replica load balancing, noise-cancellation A/B, WER and latency measurement.

**Repo hygiene**
- README links to `CLAUDE.md`, which is not in the repo.
- No commits yet. Everything is untracked on `master`, while the main branch is `main`.

**Open questions (need a human or credentials)**
- Prisma streaming support for the target language, credit cost per Gnani call, whether noise cancellation helps Prisma, whether LiveKit turn detection can change mid-session, and which embedding model works for the target language. The target language was assumed to be Marathi.
