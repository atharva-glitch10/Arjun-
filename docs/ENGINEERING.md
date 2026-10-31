# Arjun: engineering notes (2026-10-31)

How the "learn important" topics from the brief show up in this codebase: where to look, why it was built that way,
and what is still missing. Every claim points at code or a test. Numbers are only the ones we measured.

## 1. Microservice architecture

```
 elder device (React, hands-free) ──LiveKit──▶ voice-agent ──HTTP──▶ reasoning ──HTTP──▶ core-api ──▶ SQL
 family dashboard (React) ──REST + WebSocket──▶ core-api                           ▲
 scheduler (poll loop, 30 s) ──HTTP──────────▶ core-api, reasoning ─────────────────┘
```

| Service | Owns | Never does |
|---|---|---|
| `core-api` | all state (SQL), validation, the family feed (WS), undo | talk to the LLM or Gnani |
| `reasoning` | one turn: safety rules → intent → action → reply; Sarvam calls; conversation summaries | store anything itself (state is in core-api; drafts/history are in memory only) |
| `voice-agent` | Prisma STT, Timbre TTS, the LiveKit room, screen attributes | business logic (it only calls reasoning) |
| `scheduler` | time: due reminders, medicine ticks, delivery sweep, summary flush | decide anything (it only triggers endpoints) |
| `web` | the two UIs | hold secrets (the dev proxy injects the key) |

Contracts are HTTP + JSON (`shared/schemas/*.json` for LLM output). Services share contracts, not code: the token
bucket exists twice on purpose (`core_api/ratelimit.py`, `reasoning_svc/ratelimit.py`).

## 2. Latency (the "app is lagging" problem)

Measured before (STATUS.md, 2026-10-24/26): end of speech → Arjun speaking, median **4174 ms** (5 turns); one
`/turn` round trip median **351 ms** after the `localhost` → `127.0.0.1` fix (was 2334 ms).
Where the rest went: endpointing wait (1.0 s minimum), Prisma final transcript, a NEW Timbre WebSocket per reply
(~0.9–1.2 s connect, measured), then first audio.

Changes on 2026-10-31 (each is a lever, none re-measured live yet):
- **Timbre over SSE** (`agent.py: SseTimbre`): one pooled HTTP session, no WebSocket handshake per reply, and LiveKit
  sends each *sentence* as soon as it exists (the TTS is marked non-streaming so the StreamAdapter chunks it).
- **Endpointing 1.0/3.0 s → 0.7/2.5 s**, then (night of 2026-10-31) **mode-aware**: care 0.8/2.5 s, chat 1.6/4.0 s, plus a hold
  for sentences ending in a conjunction and VAD turn detection (`voice-agent/endpointing.py`). Chat answers ~0.9 s later by design; unmeasured live.
- **No question round-trip**: a reminder is one turn instead of two (no "हो" turn).
- **Sarvam thinking off** (`reasoning_effort: null`): no hidden reasoning tokens before the answer.
- **Work after the reply**: activity time and the conversation buffer are FastAPI background tasks.
- **Thinking marker** ("विचार करतोय…") so the wait is visible, not silent.
- Smoke run on the cloud box (rules only, no LLM): `/turn` 31–125 ms per turn.

To measure next: `logs/turns.jsonl` already splits endpointing / reasoning / TTS per turn (`turnlog.py`).

## 3. Concurrency

- Delivery claim is atomic in SQL (`deliveries.claim_delivery`, a conditional UPDATE): two sessions never speak the
  same reminder (`test_deliveries.py` runs it from threads).
- One speech lock in the agent: a reply, a reminder and a closing line never overlap (`agent.py: speech_lock`).
- LLM: at most `LLM_MAX_CONCURRENT` calls in flight (`evon.Limiter`, a non-blocking semaphore). A voice turn never
  waits in a queue: over the limit, the rules answer at once.
- Feed WebSocket: sync endpoints run in worker threads, sockets on the event loop; `feed.Broker.notify` crosses with
  `loop.call_soon_threadsafe`. A socket also re-checks SQL every 5 s, so a missed wake-up only delays.
- Known limit: drafts, chat history, undo memory and the conversation buffer are per process (one reasoning
  replica). Two replicas would need them in core-api or Redis.

## 4. Rate limiting

| Where | Key | Limit | Over it |
|---|---|---|---|
| core-api HTTP (`ratelimit.RateLimitMiddleware`) | client address | 30/s, burst 60 | 429 + `Retry-After` |
| reasoning `/turn` | user id | 2/s, burst 6 | 429 → the voice agent speaks its fallback line |
| Sarvam calls (`evon.Limiter`) | process | 60/min | rules answer |
| Sarvam 429 | process | cool-down for its `Retry-After` (1–300 s) | rules answer, no retry storm |

Token bucket: `burst` tokens, refilled at `rate`/s, one per request (`test_token_bucket_allows_a_burst_then_refills`).
`/health` and WebSockets are exempt.

## 5. Polling vs WebSocket (family dashboard)

- **Push**: `WS /ws/users/{id}/feed?after=N` sends `{"type":"event",...}` the moment a row is committed, `ping` when
  idle. Every Notification and Wellbeing row becomes a FeedEvent in a SQLAlchemy `before_flush` hook, so no endpoint
  can forget to publish.
- **Fallback**: `GET /users/{id}/feed?after=N` returns the same rows with the same ids. `web/src/family/feed.ts`
  loads over REST first, opens the socket, polls every 5 s while the socket is down, and retries the socket at
  1/2/5/10/30 s. `mergeFeed` de-duplicates by id, so overlap is harmless.
- Still polling on purpose: the emergency alarm (15 s, also in a background tab), the dashboard refresh (10 s while
  visible), the elder screen's cards (5 s). Polling is simple and survives proxies; push is used where seconds matter.

## 6. Error handling

- **Never silence**: a reasoning failure becomes a fixed spoken line (`bridge.reply_or_fallback`); a TTS failure
  speaks the fallback; core-api down → fixed error template; safety replies work with core-api AND the LLM down.
- **Fail closed**: core-api refuses to start without `CORE_API_KEY`; a bad WS key closes with 4401.
- **No half states**: if an auto-confirm fails, the proposal is withdrawn (`TurnEngine._act`), and a failed turn
  drops any half-built reminder draft (both found in the 2026-10-31 smoke run; regression tests in
  `test_no_questions.py`).
- **Graceful degradation**: Timbre v3.0 is probed once per worker; on failure the verified v2.5 + Omkar is used
  and tags are stripped. No Sarvam key → rules-only mode.
- **Bug found by running it**: row timestamps used the machine clock while `get_now` used the household clock.
  On a UTC machine (Docker) every action expired the instant it was proposed. Fixed in `models.utcnow`.

## 7. Boundary analysis (edge cases the tests pin)

Time: "१०:३०" (native numerals), "दहा वाजता" without सकाळी/संध्याकाळी → asks, a time already past → asks again, midnight
day boundaries, undo at 150 s vs 180 s windows. Language: Devanagari + roman, chandrabindu/nukta spelling folds,
"मला एकटं नाही वाटत" (negated) is not lonely, "लहानपणी मी एकटी होते" (past) is not lonely. Recognizer junk
("हो हो हो कर कर कर…") collapsed. Feed: `after=0` first load, unknown severity ignored, cap 200. Rate limits:
exactly `burst` then 429. Voice tags: unknown tags removed, max 2, case normalised.

## 8. Identity management and encryption (honest status)

Today: one shared service key (`X-API-Key`, constant-time compare), injected by the Vite dev proxy so it never
reaches the browser bundle; LiveKit tokens are short-lived, minted server-side, one fresh room per session; secrets
live only in `.env` and are never logged (`test_repo_hygiene.py`). Transport encryption: LiveKit Cloud is
TLS/DTLS-SRTP; Gnani and Sarvam are HTTPS. **Not built** (frozen in CLAUDE.md until after Nov 10): per-person
login, elder vs family roles, encryption at rest for the SQL file, HTTPS for the local web server.

## 9. Frontend API calls

All calls go through `/core/*` on the same origin (`web/src/api.ts`, one `call()` helper that throws on non-2xx).
The dashboard never blanks on a failed refresh (keeps the last data and says so). The elder screen never calls
reasoning: it talks only through LiveKit; the screen mirrors agent attributes (`voice/state.ts: shownFor`).

## 10. Visualization / problem solving

The family sees one headline (seriousness chip + mood + last summary), then the live feed, then the day. Colour is
never the only signal: every level has words ("All well", "Keep an eye", "Call her soon", "Emergency").

## 11. Business and technical impact

- Elder: zero buttons, no yes/no interrogation; reminders in one sentence; a reply to loneliness that points to a
  real person by name. Family: knows within seconds when it matters (push + alarm), sees a calm day as a calm day.
- Technical: the LLM is optional and boxed in (validated JSON, limits, rules floor), so a provider outage or bill
  limit degrades conversation quality, never safety or reminders.
- Costs not yet measured: Prisma credits for an always-open session (hands-free keeps the mic streaming), Sarvam
  tokens per day, LiveKit minutes.

## 12. Software engineering fundamentals

Tests first for every decision that must not be wrong (pure functions: `shownFor`, `restingScreen`, `mergeFeed`,
`split_voice_tags`, `Tracker.entry`, token buckets), one commit per task, lint (ruff) + strict TypeScript, and
"verified" only for what was actually run (STATUS.md keeps the line between tested and hand-tested).
