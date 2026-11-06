# Issues

Severity is about the Nov 8 demo plus the safety rules in `CLAUDE.md`. Confidence is how sure I am the finding is real, not how sure I am it matters. Evidence comes from Graphify edges and from reading the code.

## Checked and clean

- **Circular dependencies: none.** The file-level import graph (480 edges, 201 files) has no cycle and no strongly connected component larger than one file.
- **Dead code: little.** Graphify flagged 221 callables with no incoming edge. Almost all are FastAPI route handlers (decorator-registered), Pydantic models, `__init__`/`__call__` methods, or the YouTube iframe API types in `MediaScreen.tsx`. I did not count those as dead.
- **Cross-service imports:** services only share `shared/schemas/*.json`; they do not import each other's code (the 7 `eval -> reasoning` edges are the offline eval harness).

## Security-sensitive paths

| # | Issue | Evidence | Severity | Confidence |
|---|---|---|---|---|
| S1 | **The tunnel gives the whole API to anyone with the URL.** `web/vite.config.ts` injects `X-API-Key` into every `/core/*` request, and `allowedHosts` accepts `.trycloudflare.com`. `scripts/dev-up.ps1 -Phone` points a public quick tunnel at port 5173. Anyone who opens the tunnel URL can call every core-api route (read stories, medicines, contacts incl. phones; create or delete data) without a key. | `vite.config.ts` lines 4-5, 11-19; `dev-up.ps1` tunnel section; all routers use the same `require_key` | **High** (while a tunnel is up) | High |
| S2 | **No per-user authorization.** One shared key; `user_id` is a path parameter and is never checked against the caller. | `deps.py::require_key`; all `/users/{user_id}/...` routes | Medium (single household demo) | High |
| S3 | **`reasoning` has no authentication.** `/turn`, `/delivery/*`, `/opener`, `/conversations/flush-idle` take any caller. Safe only because uvicorn binds to loopback in `dev-up.ps1`. `docker-compose.yml` publishes `8001:8001`. | `reasoning_svc/main.py` (no `Depends`); `docker-compose.yml` | Medium | High |
| S4 | **WebSocket accepts the API key in the query string** (`?key=`). URLs end up in proxy and tunnel logs. | `feed.py::_ws_key_ok` | Low-Medium | High |
| S5 | **Default secrets in `docker-compose.yml`:** `CORE_API_KEY` falls back to `dev-change-me`; Postgres password is `arjun`. Compose publishes ports 8000 (core-api), 8001 (reasoning) and 5173 (web) on the host; Postgres is not published. | `docker-compose.yml` | Medium if compose is ever used outside the laptop | High |
| S6 | **RSS fetch of family-entered URLs follows redirects.** `applinks.https_url` blocks http, userinfo and IP literals, but a hostname can still resolve to a private address, and `http_get` uses `follow_redirects=True`. | `media.py::http_get`, `_fetch_feed`; `applinks.py::https_url` | Low (only the family can add links) | Medium |
| S7 | **Join links are not single-use.** A 30-minute HMAC link can be replayed until it expires; each use mints a 1-hour mic-publishing JWT. Falls back to `CORE_API_KEY` as the HMAC secret when `JOIN_SECRET` is unset. | `joins.py::verify`, `_secret`; `family_call.py` | Low-Medium | High |
| S8 | **Rate limiting is per client address, but behind the proxy/tunnel every call comes from 127.0.0.1.** One noisy tab can lock out the whole household. | `core_api/ratelimit.py` (per-address bucket) | Low | Medium |
| S9 | **Elder text goes to a third-party LLM** before the AI-disclosure check and on every non-safety turn. Documented, and demo data is synthetic. | `turn.py::handle` calls `_understand` before the `_AI_QUESTIONS` check | Info | High |

Good practice found: constant-time key comparison; startup refuses an empty `CORE_API_KEY`; the Telegram code logs only the exception type, never the URL that holds the bot token; YouTube errors log only the type.

## Tight coupling and separation of concerns

| # | Issue | Evidence | Severity | Confidence |
|---|---|---|---|---|
| C1 | **`TurnEngine` is a god class.** 2,204 lines, about 145 methods, 162 graph edges on `.handle()`, 14 outgoing file dependencies. It mixes safety, LLM orchestration, YouTube card state, check-in answers, delivery rendering, briefing, medicine and companion chat. In-memory per-user dicts (`_drafts`, `_media_choice`, `_last_done`, `_history` ...) hold state. | `reasoning_svc/turn.py`; graph god nodes | Medium (hard to change safely just before a demo) | High |
| C2 | **`Dashboard.tsx` is 1,155 lines** with 13 imports and the whole page in one component. | graph: 88 edges | Low-Medium | High |
| C3 | **`core_api/main.py` mixes routing and business logic** (767 lines, 34 handlers; undo and distress logic live in handlers). Other features were split into routers, this one was not. | `main.py::undo`, `record_distress` | Low-Medium | High |
| C4 | **core-api <-> reasoning share an implicit contract.** `CoreClient` has 40 methods that hard-code core-api paths and payload shapes; there is no shared client or schema for them (only `intent.json`). A route rename breaks reasoning at run time only. | `core_client.py` | Medium | High |
| C5 | **Feed is a side effect of a SQLAlchemy `before_flush` hook.** Any new `Notification` or `Wellbeing` becomes a feed row, which is robust, but it hides coupling between `feed.py` and every module that writes notifications. | `feed.py::_to_feed` | Low | High |

## Duplicates

| # | Issue | Evidence | Severity | Confidence |
|---|---|---|---|---|
| D1 | **Two media-action pipelines in the browser.** `voice/state.ts::parseActionAttribute` -> `elder/media.ts::planAction/embedSrc` (used by `useAppActions`) and `voice/action.ts::parseAction/embedSrc` (used by `MediaScreen`, `Gallery`). Two `embedSrc` functions with different signatures. | grep shows both in use | Medium (drift risk: one can change without the other) | High |
| D2 | **Emergency lexicon exists twice.** `voice-agent/safety_words.py` is a copy of `reasoning/distress.py`. This is deliberate ("services share contracts, not code") but a phrase added in one place and not the other makes media mode swallow it. | file header says so; no test compares them | Medium (safety) | High |
| D3 | **`TokenBucket` twice** (`core_api/ratelimit.py`, `reasoning_svc/ratelimit.py`) and **timezone logic three times** (`core_api/deps.py`, `reasoning_svc/clock.py`, `scheduler.today_local`). | graph + grep | Low | High |
| D4 | **Duplicate routes:** `/users/{id}/app-links` and `/users/{id}/apps` (GET, POST, PATCH, DELETE each). | `applinks.py` | Low | High |

## Dead, orphaned or stale

| # | Issue | Evidence | Severity | Confidence |
|---|---|---|---|---|
| O1 | **Stray files committed in the repo root:** `appcmd.txt`, `f4.txt`, `final.txt`, `final2.txt`, `final3.txt`, `one.txt`, `one2.txt`, `q.txt` (~158 KB, tracked by git). They look like pytest output dumps (I read the first bytes of two and ran the secret-pattern grep on all eight: zero hits). Clutter, not a leak. | `git ls-files` | Low, but Medium if public | High |
| O2 | **`shared/schemas/tool_calls.json` has no inbound reference** in code, tests, scripts or eval. Possibly documentation only. | Graph: no edge; grep found none | Low | Medium |
| O3 | **Frozen features are built:** BP readings and watch samples (`core_api/readings.py`, `reasoning_svc/readings.py`, `BpReading`, `WatchSample`, `_record_bp` in the turn path). `CLAUDE.md` says "frozen, do not build without asking". They cost turn-path code and attack surface. | `models.py`, `main.py` mounts `readings_router` | Low-Medium (scope) | High |
| O4 | **Legacy `Evon` naming** for the hosted-LLM client (`evon.py`, `EvonClient`, `EVON_*` aliases) while Evon is "not used". Confusing for anyone reading the code or the write-up. | `evon.py` | Low | High |
| O5 | **Stale comment:** `_safety` docstring says "emergency policy is PENDING a decision", but the decision (always alert) is made and implemented. | `turn.py` `_safety` | Low | High |
| O6 | **`docker-compose.yml` lacks voice-agent** and defaults `ARJUN_ASK_BEFORE_ACTING` to `0` while the root docs describe both modes. Compose cannot reproduce the demo. | `docker-compose.yml` | Low | Medium |
| O7 | **`.db` files sit inside service folders** (`services/core-api/arjun*.db`, `services/reasoning/arjun.db`). Git ignores them; they are not tracked. A `reasoning/arjun.db` is odd because reasoning should not own a DB. | `ls`; `.gitignore` | Low | Medium |

## Scalability bottlenecks

| # | Issue | Evidence | Severity | Confidence |
|---|---|---|---|---|
| B1 | **State held in process memory:** active LiveKit rooms (`livekit_token._rooms`), Telegram dedupe (`telegram._last_attempt`), news cache, rate-limit buckets, scheduler "opened today", and most `TurnEngine` per-user dicts. A restart or a second replica loses or splits them. Fine for one household demo. | modules named | Low now, High for any multi-instance deploy | High |
| B2 | **Scheduler can repeat an opener/briefing after a restart** (admitted in the code comment). | `scheduler.py` | Low | High |
| B3 | **Feed WebSocket re-queries the DB every 5 s per open socket**, plus REST polling fallback. | `feed.py::RECHECK_S` | Low | High |
| B4 | **Blocking calls in the turn path:** reasoning is synchronous; each turn does several sequential HTTP calls to core-api plus one LLM call (up to ~4 s). Voice-agent waits at most 5 s, then speaks the fallback. | `bridge.py`, `turn.py::handle` | Medium for latency | High |
| B5 | **No migrations:** `create_all` plus a hand-written add-column step. Documented as frozen. | `db.py` | Low | High |
| B6 | **SQLite with `check_same_thread=False`** is the default; the Telegram thread and WS handlers use separate sessions. OK for one process. | `db.py` | Low | Medium |

## Unnecessary dependencies

I did not inspect `requirements.txt` or `package.json` contents, and Graphify found no cycles or unused imports. Graphify showed `httpx` (73 edges) and `json` as the most-used external nodes, which is expected. I have no evidence of an unnecessary package, so I list none.
