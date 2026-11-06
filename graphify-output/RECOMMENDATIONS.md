# Recommendations

Ordered by value for the Nov 8 submission. IDs refer to `ISSUES.md`. Nothing here was applied; no application code was changed.

## Before Nov 8 (quick wins, low risk)

1. **Close the tunnel hole (S1).** While a quick tunnel is up, the Vite proxy hands the API key to anyone with the URL. Cheapest fixes, pick one:
   - make the proxy allow only the routes the two pages need (`/core/livekit/token`, `/core/family/join`, the feed, the day/reminder/medicine reads) and refuse the rest; or
   - put HTTP basic auth or a Cloudflare Access rule in front of the tunnel; or
   - keep the tunnel up only during recording and shut it afterwards.
   Also never post the tunnel URL in public material.
2. **Add a test that the two emergency lexicons match (D2).** One small test that imports both lists and asserts the voice-agent set is a superset of the reasoning set. This protects "a fall" and "chest pain" from being swallowed during video playback.
3. **Remove `?key=` from the WebSocket path (S4)** by letting the proxy add the header (it already does), and make `_ws_key_ok` header-only.
4. **Set a real `JOIN_SECRET` (S7)** in `.env` so join links are not signed with the API key. Optionally shorten the link life to 10 minutes.
5. **Delete or move the 8 stray `.txt` dumps from the repo root (O1)** and add `*.txt` pytest-output patterns to `.gitignore`.
6. **Fix small stale items:** the `_safety` docstring (O5); drop `tool_calls.json` if nothing uses it (O2, confirm first).
7. **Do not run `docker compose` for the demo (S5, O6)** unless you first change the default key and database password; it also lacks the voice agent.
8. **Say plainly in the write-up** that the conversation LLM is the hosted non-Gnani model and that elder text in open-chat turns goes to it (S9). The root docs already require this.

## After the contest (structural)

1. **Split `TurnEngine` (C1).** Suggested seams, in order of least risk: media cards (`_open_media` ... `_next_page`), delivery rendering (`deliver_next`, `_medicine_line`, `_checkin_line`), check-in answers, companion/chat. The safety path stays in the first lines of `handle` and should be extracted last. Keep the 100+ existing tests green after each move.
2. **One browser media pipeline (D1).** Merge `voice/action.ts` and `elder/media.ts` + `state.ts::parseActionAttribute` into a single parser and a single `embedSrc`.
3. **Real authentication (S2, S3).** Per-user tokens for the browser, a service-to-service secret on `reasoning`, and no key in the browser path. This is already in the frozen list ("login/roles").
4. **Typed client between reasoning and core-api (C4).** Generate it from core-api's OpenAPI schema so a renamed route fails the build.
5. **Break up `Dashboard.tsx` (C2) and `core_api/main.py` (C3)** into feature components and routers (reminders, stories, actions, safety).
6. **Share small utilities (D3):** one `TokenBucket` and one household-clock helper, in a tiny shared package or copied with a test.
7. **Collapse duplicate routes (D4)** once the web app uses only one of `/apps` and `/app-links`.
8. **Rename `evon.py` / `EvonClient` to `llm.py` / `LlmClient` (O4)** and drop `EVON_*` aliases after the contest.
9. **Move in-memory state to the database or Redis (B1, B2)** before running more than one process: active rooms, Telegram dedupe, scheduler "done today" flags.
10. **Review the frozen features that are already in the code (O3).** Either feature-flag BP and watch routes off, or record the decision to keep them.
11. **SSRF hardening for RSS (S6):** resolve the host and refuse private ranges, and turn off redirects or re-check each hop.

## How to keep the graph useful
Run `graphify update .` after code changes (AST only, no API cost). A docs-aware graph (README, STATUS.md, `docs/ENGINEERING.md`) needs semantic extraction, which this run skipped on purpose (`--code-only`).
