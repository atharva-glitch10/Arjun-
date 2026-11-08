# STATUS (2026-11-04, LLM-first understanding + companion context)

## Prisma v3 handshake refused on the laptop (2026-11-08 21:52)
- `GNANI_STT_IMPL=v3` failed every connection. Gnani reason (now logged, 21:55): "exactly one locale is required" for
  `language_code`; several languages now send `indic-auto`. Earlier also fixed: likely
  cause: Devanagari keyterms/speaker names sent raw in WS headers (`ensure_ascii=False`); Gnani's docs require
  escaping. Now ASCII-escaped, and a refused handshake logs Gnani's own reason. Unit-tested; not yet verified live.

## Hinglish answered in Marathi; "हीराबाईबाई" (2026-11-08 21:46, laptop)
- With the plugin STT locked to mr-IN, Hindi/Hinglish was transcribed fine but labelled mr-IN, so replies stayed
  Marathi. Prisma v3 (`GNANI_STT_IMPL=v3`) now hints the elder's languages + hi-IN + en-IN (`GNANI_STT_LANGUAGE_HINTS`).
  Unit-tested; v3 on the laptop not yet verified live.
- Address fallback added "बाई" to a name already ending in "बाई". Fixed in reasoning `turn.py`.

## Held sentence never answered (2026-11-08 21:36, laptop)
- "नमस्कार अर्जुन" (2 words) was held for more speech; the next speech produced no words, so no turn ever completed
  and the held text was never answered. Now a held part is answered after `ARJUN_HELD_ANSWER_S` (default 4 s) with no
  new words. Unit-tested (`test_held_watchdog.py`); not yet heard live.

## Arjun speaks again; cloned voice heard live (2026-11-08 evening)
- Root cause of "answers on screen, never speaks": `session.say(text, tts=...)` (since 66e76d0) - LiveKit 1.8.6
  `say()` has no `tts`; every reply raised TypeError. Fixed with `say(audio=tts_audio(...))`;
  `test_say_signature.py` guards it. **Verified live on the laptop:** a Marathi turn was heard (Prisma, mr-IN),
  answered in ~2 s and spoken in the cloned voice (21:29). User feedback: the clone's Marathi sounds Hindi-like.
- Cloned-voice SSE streaming exists but is OFF by default: on the laptop (21:41) it produced loud noise and started no
  sooner than REST (~3.3 s). Default `ARJUN_CLONED_VOICE_METHOD=rest` (clean audio heard at 21:29). `ARJUN_CLONED_VOICE_LANGUAGES` limits which detected
  languages may use the clone (Gnani's voice-clone API documents no language field).

## Voice cloning, voice diagnostics, single session (2026-11-08)
- **Voice cloning (consent-first)** merged (#2-#4): family dashboard "A familiar voice"; Gnani voice-clone embeddings
  called once by core-api (CLAUDE.md rule 12 exception, PROPOSED); only the Fernet-encrypted embedding is stored
  (`VOICE_CLONE_KEY`); companion chat only via `vachana-vc-v1`; safety/medicine/reminder/confirm/action/fallback always
  Timbre; cloned-TTS error or silence falls back to Timbre. **Verified live:** adding a voice on a real laptop (Gnani
  accepted the WAV). **NOT verified live:** hearing a cloned reply (no full spoken turn ran yet).
- **Arjun silent on the laptop (open):** a 2026-11-08 log showed the mic stream read for ~20 s and no transcript, no
  turn, no error. Root cause NOT found yet. Added `ARJUN_DEBUG_VOICE` (default on) logging per step, never the words:
  `voice: user listening -> speaking`, `stt interim/final (chars, language)`, `turn -> reasoning`, `turn answered in N ms`,
  `reply voice: ...`, `error detail` (keys scrubbed), plus a warning when speech is detected but Prisma returns nothing.
- **Duplicate rooms fixed:** a tap during the page's pre-warm join opened a second room (two Arjun jobs per elder). The
  tap now waits for the pre-warm join. Verified by reading the code path and tsc/tests, not on a device.
- **Elder UI:** medicine screen no longer gets stuck when a tap is refused (409/404 closes it; other errors shown in
  red) - verified in headless Chromium with mocked core-api. Familiar-voice chip never on medicine/safety/confirm.
- Verification (this sandbox, no Gnani/LiveKit network): core-api 306, reasoning 984 (+1 skipped), voice-agent 356,
  scheduler 7, web 146, tsc, ruff, `eval/run_eval.py` (distress 5/5, emergency 87/87, false alarms 0/12).

## Logical companion replies (2026-11-08)
- Baseline from local turnlog: 128 turns, 1 fixed fallback (0.8%), 69 LLM replies, and 11 system-marker turns; 5 `[video_call_stopped]` markers reached the LLM. The single fallback followed a 5.0 s reasoning wait, consistent with the configured voice timeout, but the log lacks enough structured causes to attribute it conclusively. Sanitizer, malformed-JSON, busy/429, cut-off, and garbled-STT counts are not recoverable from those historical rows.
- Removed routine generic “didn't hear/understand” lines. Empty/noise input is silent once and gets a warm proximity prompt after two consecutive noise turns. Uncertain content gets a topic-specific clarification; markers are handled as events before LLM. Safety path remains first. Companion endpointing merges short/conjunction fragments for at most 1.5 s; reply timing is bounded by the configured LLM budget and understanding retries once with shorter context.
- Prompt now asks the model to answer the elder’s actual last sentence, use transcript error tolerance, preserve facts/history, and clarify specifically. Sanitizer rejection gets a corrective retry and a topic-aware final response. TTS errors no longer trigger an unrelated spoken fallback.
- Sarvam scores for the last 50 historical LLM replies were not requested from the provider: no `SARVAM_API_KEY` or synthetic evaluation user/reasoning URL is configured, and historical conversation text is not sent to a judge. `eval/logic_eval.jsonl` contains 80 synthetic cases; `scripts/eval_logic.py` requires those explicit environment values to execute. No before/after provider judge score is claimed.
- Verification: core-api 298, reasoning 994, voice-agent 352, scheduler 7; Vitest 146, TypeScript, production build, Ruff, and `eval/run_eval.py` pass. Build reports the existing >500 kB bundle warning. Full local pytest cache writes remain denied; workspace-local basetemp was used.

## Accounts and per-user authorization — Phase 1 (2026-11-07)
- Added opt-in `ARJUN_AUTH=1` core-api account/session/membership/device auth. Default `0` and service `X-API-Key`
  behavior remain compatible. Argon2id hashes passwords; sessions use HttpOnly cookies; invite and device-pairing
  credentials are single-use and hashed in SQL. Family accounts are checked against each elder membership, and elder
  device credentials are bound to one user. WebSocket feed requests receive the same membership check.
- Added `accounts`, `memberships`, `sessions`, `devices`, `invites`, and `pairing_codes` tables through the existing
  `create_all` startup mechanism. No `.env` values or database files were changed. Compose accepts the opt-in flag.
- Auth tests: 4 passed. Full verification: core-api 297, reasoning 987, voice-agent 335, scheduler 7, web 146;
  TypeScript, production build, Ruff and `eval/run_eval.py` pass. Pytest used workspace-local `--basetemp` because
  the account's system temp directory denies access. The current web tunnel still uses its service-key role gate;
  browser login/proxy integration is Phase 2, so leave `ARJUN_AUTH=0` until that integration is available. Shared
  reasoning and active-call state for multiple workers are Phase 3 and are not implemented.


## Daily Telegram voice briefing (2026-11-07)
- Added core-api `build_briefing(user_id, date)` using current-day medicine doses, raw BP readings, meal check-ins, and
  consent-gated mood/paraphrased conversation summary. Text stays in memory for the request only; transcripts and briefing
  text are not stored or logged. Sugar values are omitted because the database has no sugar-reading model.
- Added Telegram `sendVoice`, a per-user/local-date attempt record, honest `briefing_sent` / `briefing_failed` feed events,
  a force-send dashboard button, and a scheduler sweep gated by `BRIEFING_TIME` (default 20:30) and `daily_checkins`.
- The voice-agent process serves the protected loopback OGG/Opus synthesis endpoint. Plugin 1.8.6 exposes OGG/Opus and
  declares model ids v2.0/v2.5. A real one-word key-backed probe resolved to the known fallback `timbre-v2.5` / Omkar;
  configured v3.0 failed its probe, so the unverified model/tag path was skipped. No Telegram poller exists, so `/summary`
  was not added.
- Verification: core-api 287, reasoning 982, voice-agent 325, scheduler 7, Vitest 145; TypeScript, production build,
  Ruff and eval pass. A synthetic WAV converted to valid OGG locally. A real Timbre OGG request was blocked because this
  sandbox could not reach `api.vachana.ai`; Telegram delivery and physical-phone playback still need the hand test in
  HANDOFF.md. No `.env` values or database files were edited.

## Daily health check-ins enabled for the demo user (2026-11-07)
- Root cause of "Arjun never asks": user 1 had `daily_checkins=0`, and the plan had no seeded profile times, so
  `ensure_checkins` returned early and the tick loop skipped the user. The DB was correct; the seed/profile was not.
- Demo seed (`scripts/seed_heerabai.py`) is now idempotent and sets user 1: check-ins ON, opener 07:30-21:00,
  wake 06:30, breakfast 08:30, lunch 13:00, snack 17:00, dinner 20:00, walk 18:00, BP 09:00, fasting sugar 08:00,
  after-lunch sugar 15:00, address "आजी", and four medicine rows (बीपीची गोळी 09:00/21:00, शुगरची गोळी
  08:30/20:30). Medicines not in that plan are switched off. `name` cannot be PATCHed, so the stored name stays
  "Demo Aaji (synthetic)"; the spoken address is आजी.
- New optional `users.sugar_check_time` / `sugar_after_time` columns (added by `ensure_columns`), dashboard fields,
  and `sugar` / `sugar_after` check-in kinds. `walk_time`, `bp_check_time` and both sugar times are omitted from the
  plan when unset.
- Engine defaults changed: quiet hours 22:00-06:30; `ARJUN_CHECKIN_MAX_PER_DAY=14` counts only non-routine prompts;
  meals / snack / walk / BP / sugar are exempt; `ARJUN_CHECKIN_MIN_GAP_MIN=30`; each decision is logged once as
  `checkin <kind> asked|postponed:<reason>|missed`. The scheduler now fills empty `OPENER_USER_IDS` /
  `BRIEFING_USER_IDS` from `GET /internal/checkin-users` (every user with `daily_checkins=True`).
- Dashboard: both sugar times are editable and the check-in switch is a clearly labelled ON/OFF toggle.
- Deferred to Phase 2 (not in this change): the full deterministic routine (water / wellbeing / reflection / night /
  company prompts), sugar-number reading, appointment/festival/loneliness planning, the elder "आजचा दिवस" timeline
  and the family trends/adherence screen.
- Phase 1 verification (2026-11-07): core-api 280, reasoning 976, voice-agent 322, scheduler 8, web 144; TypeScript,
  production build, Ruff and `eval/run_eval.py` (46/46 intent, 12/12 slots, 5/5 distress, 87/87 emergency,
  0/12 false alarms) all pass. Tests used a workspace-local pytest temp root because system temp enumeration is denied.
- Follow-up runtime audit: live core-api confirms the seeded profile and check-in switch are active. Scheduler logs
  contain repeated ticks and `check-in due, queued for delivery user=1 lunch`; the current delivery API still shows that
  item queued, with no corresponding spoken entry in the newest voice-agent logs. The voice log therefore does not
  prove an elder session was connected when it became due. During a family call, the voice loop previously skipped
  delivery lookup entirely, leaving check-ins queued without the busy/postpone decision. It now reports call-active
  separately: check-ins are postponed and no reminder/medicine is claimed for speech until the family leaves. Added
  regression coverage for both; corrected the demo's 30-minute gap and quiet-hours descriptions. Phone verification is
  still needed to prove actual audio delivery.


## YouTube playback no longer strands listening (2026-11-07)
- Root cause evidence: newest media session logged `ignored_media (54 characters; the words are not kept)` on later turns after `OPEN_MEDIA`; then `stream closed ... SOURCE_MICROPHONE`, `input stream detached`, and `session closed {"reason":"participant_disconnected"}`. This confirms the media gate was discarding later recognized speech. The disconnect cause itself is not proven to be YouTube opening a new tab; YouTube was already handled by an in-page iframe.
- Media mode now starts only after the embedded player reports `playing`, receives a changing 10-second heartbeat, and turns off for stop/end/error/unmount/page hidden or a 30-second heartbeat timeout. Mode transitions log once with a reason.
- Media stop notifies reasoning to clear pending media question/choice and store one `[media stopped]` history note. Safety still passes during playback; supported bare controls include stop/back, pause, next/previous, and volume. The page ducks video to 20% while VAD reports speech, then restores volume; long media utterances commit at 8 seconds.
- Elder page recovers LiveKit on visible/pageshow/focus, recreates a disconnected room with bounded backoff, republishes an ended/muted/missing mic, resumes LiveKit audio and attached audio elements, and resends media state on joining. Echo cancellation, noise suppression, and auto gain remain enabled. A Gnani STT error requests a fresh LiveKit session, which creates a fresh STT stream.
- Automated verification: voice-agent 318 passed; reasoning 969 passed; core-api 269 passed; scheduler 8 passed; web 139 passed; TypeScript, build, Ruff, and `eval/run_eval.py` passed (42/42 intent, 12/12 slots, 5/5 distress, 87/87 emergency, 0/12 harmless false alarms). No live phone or Gnani STT-restart test was run; perform the checklist in HANDOFF.md.

## Gnani Prisma v3.0 audit (2026-11-07)
- Audited the installed/pinned `livekit-plugins-gnani==1.8.6` constructor: it has no explicit Prisma model argument and exposes only `verbatim`/`transcribe`, not v3 `codemix`/`transliterate`, Auto-LID, keyterms, named speakers, or previous-context controls.
- Current configured path remains plugin-selected STT, `mr-IN`, streaming, 16 kHz, `transcribe`, native numerals. These settings are not evidence of explicit `prisma-v3.0` selection.
- Added fail-fast validation for supported format, language hint, and sample rate; unsupported Auto-LID and modes are rejected. No protocol adapter was attempted because the pinned SDK does not document the v3-specific request/response messages.
- `scripts/check_gnani.py` now safely checks key presence/whitespace and configured model labels without making a request or printing secrets. It does not test authentication.
- Timbre config remains `timbre-v3.0` / `Avinash` with fallback `timbre-v2.5` / `Omkar`. v3.0 is not live-verified; historical live evidence is v2.5 only. No live Prisma or complete spoken-turn verification.

### Documentation follow-up
Official Gnani Prisma v3.0 product and SDK docs now describe model selection, `indic-auto`, language candidates,
all four modes, keywords, topic, speaker names, previous text, and detected-language metadata. This corrects the
earlier note that official docs were unavailable. It does not confirm this competition account has access, nor
does it make these options available through the pinned LiveKit plugin. Streaming wire mappings for all context
fields remain unclear from published examples. No code or package pin was changed pending a Gnani-supported
LiveKit adapter or confirmed protocol and account check. See `docs/ENGINEERING.md` and `HANDOFF.md`.
- Focused voice-agent configuration tests previously passed (23). Full regression suites on 2026-11-07: voice-agent 318, reasoning 969, core-api 269, scheduler 8, web 139; TypeScript, production build, Ruff, and eval passed. These are local automated checks, not live account, microphone, or spoken-turn verification. The safe Gnani diagnostic checks key presence/whitespace only; it does not resolve the historical 401. See `docs/ENGINEERING.md` for current integration limits.

## Verification for latest work (2026-11-04)
- core-api: 269 passed; reasoning: 950 passed; voice-agent: 310 passed; scheduler: 8 passed.
- Web: 133 tests passed; `npx tsc --noEmit`, production build, Ruff, and intent/slot/distress/emergency evals passed.
- Dialogue run `final1` completed with d12 at 12/12 and no judge failures. Gemini then sustained throttling;
  `final2` and `final3` did not complete, so the requested three-run means remain outstanding. Repeat after recovery.
- Graphify security scan: zero requested secret/token/phone patterns. No local commits were made because the
  required three-run dialogue evaluation did not finish green.

## Latest work (2026-11-04): widened companion boundary, address form, next-day memory and LLM summaries
- Boundary 10 now permits general knowledge, festivals, meanings, everyday how-to and recipe basics; recipes are
  2-3 short steps followed by "व्हिडिओ लावू?". Medical/health/medicine advice, doses, diagnoses and model-sourced
  news facts remain blocked. Recipe how-to questions stay in chat; explicit video requests still use media.
- Consent behavior is documented in `CLAUDE.md`: facts stay available to Arjun regardless of sharing consent, the
  family list is consent-gated, body-complaint facts are consent-gated, and deletion needs no consent.
- Added editable profile `address_as`, defaulting to first name + "बाई" or "आजी" at age 60+. Old SQLite profiles
  receive a non-destructive backfill. The family dashboard can edit it; LLM context and prompt use the exact value.
- Rest agreement is allowed when she states her own plan; unprompted rest advice remains blocked. Leading "का" and
  "अहो" are stripped. Dialogue d11's fixed fallback regression is covered.
- Greetings select yesterday's latest event fact deterministically, or a recent summary topic if no event exists;
  the model only phrases the selection. Idle family summaries now request 2-3 unquoted, non-transcript lines from
  the configured LLM, with the rules summary on provider failure.
- Graphify output docs scan: 8 files, zero matches for requested secret/token/phone patterns. `graphify-out/` is
  ignored; the Markdown architecture analysis is staged for its own local documentation commit.

## Built 2026-11-04 (night): session + long-term memory, smarter companion (tests + a scripted eval on the real LLM; NOT heard with a real voice)
- **Why:** replies felt foolish and context was lost: check-in lines, tool replies and safety turns never reached the
  LLM history, silence over 30 min or a distress wiped it, `companion_reply` got no user context, and nothing lasted
  across days. Map and proof: `scripts/converse_test.py` (the four STEP 1 dialogues on the real LLM, messages[] printed).
- **Gap map (before -> fixed):** check-in / reminder lines Arjun says first never recorded -> `deliver_spoken` records
  them; `_answer_open_checkin` / BP / pending-repeat / early returns skipped `_remember` -> ONE recorder in `handle`;
  `_lonely` recorded Arjun's reply as HER words (variable reuse) -> gone with the recorder; distress wiped history ->
  kept with a note; silence deleted -> compressed into a 3-line summary; `companion_reply` had no context -> context +
  memory block; no cross-day memory -> `user_facts`; history size came from `LLM_HISTORY_EXCHANGES` (8 in a dev
  `.env`) -> own `ARJUN_SESSION_EXCHANGES` (20). Not spoken yet, so nothing to record: openers and briefings (T8).
  Not given history on purpose: the safety second look (one utterance, must stay tight), check-in and media
  classifiers (one short utterance each).
- **Built:** `reasoning_svc/memory.py`, `core_api/facts.py` (+ `UserFact`), `Tracker.remember_life`, `extract_life_facts`,
  "हे लक्षात ठेव / हे विसरून जा", `KnownFactsCard.tsx`, prompt rules, `shape_questions`, `salvage_companion`, a
  narrower "doctor" pattern in the sanitizer (mentioning the visit is not advice, "डॉक्टरकडे जा" still is),
  greeting through the companion when she has history. Env: `ARJUN_SESSION_IDLE_MIN`, `ARJUN_SESSION_EXCHANGES`,
  `ARJUN_FACTS_IN_CONTEXT` (in `.env.example`; `.env` untouched). Design: docs/ENGINEERING.md section 15.
- **Owner decisions recorded 2026-11-04:** fact storage and family visibility consent rules are documented in
  `CLAUDE.md`; boundary 10 is widened to allow everyday knowledge, how-to and recipe basics while preserving health,
  medicine, dose, diagnosis and model-news restrictions.
- **Eval (`eval/dialogues.jsonl`, 15 multi-turn dialogues, `scripts/eval_dialogues.py`, judge = the same provider,
  Gemini via `LLM_*`, temperature 0, n=1 per dialogue):** BEFORE (previous commit, same harness) vs AFTER, mean /2:
  remembers_context 1.47 -> 1.73, uses_her_life 1.33 -> 1.53, smart_answer 1.40 -> 1.80, natural 1.87 -> 1.93,
  not_repetitive 1.53 -> 1.73, sum of five 7.60 -> 8.72 /10, safe 15/15 both. Files: `eval/results/dialogues_before.json`,
  `dialogues_after.json`. Caveats: one run each; the LLM is not deterministic (an earlier AFTER run scored 8.94, an
  earlier one 7.80); the judge is lenient at times (it scored d05 as remembered even for BEFORE, when the reply only
  echoed the name). Treat +1 as real, not +1.12 exactly.
- **Resolved in latest work:** d11's agreement with her own rest plan now passes sanitization; d12's first greeting
  selects yesterday's latest event fact deterministically; idle family summaries use the LLM with the rules summary
  as fallback. Provider latency and occasional rate limits remain real deployment constraints.
- **Verified:** core-api 268, reasoning 945, voice-agent 310, scheduler 8 pytest; `ruff check .`; `tsc --noEmit`; vitest
  133; `eval/run_eval.py` 42/42, emergency recall 87/87, 0/12 false. **NOT verified:** a real voice session, the
  dashboard card in a browser, Postgres (SQLite only), facts extraction with Sarvam (only Gemini was available).

## Built 2026-11-04 (late): tunnel access lock, one safety-word source, repo cleanup (from graphify-output/ISSUES.md)
- **Tunnel lock (issue 1).** Before this, the Vite proxy added `CORE_API_KEY` to every `/core/*` call, so anyone with the
  Cloudflare URL held the whole API. Now `web/server/access.ts` (a Vite middleware + proxy hooks) decides first:
  this laptop (loopback socket + localhost Host + no Cloudflare/forwarded headers) is trusted; anything else needs the
  HttpOnly `arjun_access` cookie (role elder|family, 12 h, SameSite=Lax, Secure over https, HMAC keyed by
  `ARJUN_ACCESS_CODE` + `CORE_API_KEY`). `/?user=1&k=<code>` or `/auth?k=` swaps the code for the cookie and redirects
  without `k`. Elder cookie: day, deliveries/open, reminders, appointments/next, contacts, medicines/due, dose
  taken/snooze, delivery ack, livekit token. Family cookie: the dashboard routes (api.ts list) + feed REST + WS.
  Everything else 403, no cookie 401, bad code = Marathi page. `/core/family/join` and `/?view=join` stay public. The API
  key is added to a proxied request only when it passed, and the cookie is not forwarded. 10 wrong codes a minute -> 429.
  No code set (or < 6 chars) = every remote request refused. `scripts/dev-up.ps1 -Phone` refuses to start without the
  code, restarts web, prints the full links with the code. New var in `.env.example` only; `.env` was not touched.
- **WebSocket `?key=` removed.** core-api `_ws_key_ok` is header-only and refuses any `key` query parameter, even a
  correct one; the proxy answers 400 for it. (core-api test + proxy tests.)
- **Safety words, one source (issue 3).** `services/voice-agent/safety_words.py` is now GENERATED from
  `reasoning_svc/distress.py` by `scripts/gen_safety_words.py` (phrases, regex patterns, loanword patterns, fail-safe
  words); `test_safety_words_sync.py` fails when it is stale and checks every phrase of `eval/emergency_cases.jsonl`
  (87 emergencies) is detected by BOTH sides, and that both agree on the 12 non-emergencies. The copy now also carries
  the distress/fall PATTERNS, so media mode catches a superset of what it did before.
- **Cleanup (issue O1).** The 8 tracked pytest-output `.txt` files in the repo root are `git rm`'d; `/*.txt` is ignored.
- Noted in HANDOFF.md "After demo": per-user authorization, the `TurnEngine` split, the duplicate media pipelines.
- **Verified:** core-api 245, reasoning 894, voice-agent 310, scheduler 8 pytest; `ruff check .`; `npx tsc --noEmit`;
  vitest 133 (19 new access tests); `python eval/run_eval.py` (42/42 intents, emergency recall 87/87, 0/12 false).
  Also checked against a REAL Vite server on a spare port with curl, sending tunnel-style headers: no cookie 401,
  wrong code 403 + Marathi page, right code 302 + HttpOnly cookie, elder cookie 403 on family routes and WS, family
  cookie 403 on the livekit token, join route and join page open, `?key=` on the WebSocket 400.
- **NOT verified:** a real Cloudflare tunnel with a real phone (the tunnel's headers were imitated, not seen); a browser
  following the redirect and storing the cookie; the dashboard and elder page working end to end behind the lock (the
  route lists come from reading the code, so a route the pages call that I missed would show as 403: check the browser
  network tab on the phone). Roles are not per person (elder link for user 1 can read user 2).

## Built 2026-11-04: one LLM call understands the whole sentence, rules are only the fallback
- Why: the rule parser answered normal Marathi with "मला समजलं नाही" / "आता कसं वाटतंय?" style lines, hijacked
  sentences that merely mentioned a keyword (a story with "औषध" became a medicine question) and ignored who she is.
- `evon.understand_turn()`: ONE call per non-safety turn. The prompt gets the full sentence, the last turns and a
  USER CONTEXT block; it must answer strict JSON
  `{"intent": "chat|reminder_add|reminder_done|medicine_taken|medicine_query|media|news|call_family|
  message_family|today_query|undo|stop|health_complaint|unclear", "slots": {...}, "reply": "...", "confidence": 0-1}`.
  Legacy intent names (`OPEN_LINK`, `OPEN_WHATSAPP`, `MEDIA_CONTROL`, `MED_SNOOZE`, `TIME_QUERY`, `NEXT_UP`) are still
  accepted and marked `legacy`, and plain prose is treated as a chat reply, so old tests and a provider that ignores
  the JSON contract do not need a second call.
- Safety floor unchanged and first: emergency/distress rules + the second look run BEFORE the LLM call and work with
  the LLM/core-api down. Deterministic state answers stay rule-decided even after the call: pending yes/no, stop,
  medicine taken, time/next-up, greeting, hearing check.
- Rules are fallback only: LLM timeout, provider error, invalid JSON, unknown intent, or confidence < 0.4 for an
  action intent. Every rule-routed turn is logged with the reason (`source=rule`, `route_reason`), and no keyword
  hijack remains: a sentence that only mentions "औषध" stays chat.
- Action intents still execute the existing SQL-backed code and fixed read-backs; the LLM `reply` is used for
  `chat` / `unclear` only.
- USER CONTEXT (core-api, cached 5 min, <=700 chars): name + address form, family names/relations (never numbers),
  date/day/festival, today's medicines taken/missed, appointments/reminders, check-in answers, interests, and the last
  conversation summary only. New core-api calls: `GET /users/{id}/checkins/card`, `GET /users/{id}/wellbeing/today`.
- Companion prompt: male companion, masculine Marathi (`सांगतो`, `विचारतो`, `करतो`), respectful `तुम्ही`, noisy STT,
  NEVER ACT DUMB, ALWAYS TRY TO GIVE A SOLUTION, replies about her life, 1-2 short sentences (how-to up to 3), no
  medical advice, no human/body/family claims, no guilt, encourage family contact. "आता कसं वाटतंय?" and
  "हे अजून मला जमत नाही" are removed everywhere.
- Limits: `LLM_MAX_TOKENS` default 250, temperature 0.5, reasoning off. `finish_reason=length` trims back to the last
  full sentence instead of shipping a cut line.
- Sanitizer narrowed to what must not ship: medical advice/diagnosis, human claims, Latin script, >4 sentences or
  >300 chars (no `too_long` under 300). One corrective retry, then a fixed fallback line.
- Media behaviour preserved and pinned: empty query opens the only family favourite, a named singer/song is not
  suffixed with "मराठी", a bare category/bhajan uses a family playlist that covers it, an unknown kind with a query
  becomes a video search, results line "यूट्यूबवर शोधलं आहे. हवा असलेला व्हिडिओ दाबा."
- Two rule hijacks found by the eval and fixed: "आज माझी तब्येत बरी नाही" was read as "नाही" to an open question
  (cancelled it and said the family was told help is not needed), and "माझा चस्मा सापडत नाही" undid the last action.
  Now a yes/no is the answer only when it looks like one ("हो", "नको", "नाही, नको"), and the parser marks a
  correction only when the sentence restates a clock time.
- Measured with `scripts/eval_companion.py` (real `/turn`, throwaway SQLite, ONE throwaway user per utterance,
  Sarvam for the turn AND the judge; the old code was run from a worktree at the previous commit with `--legacy`):
  - companion eval 50 utterances, before: 46/50 turns reached a reply (4 requests failed in the old stack, 1 judge
    failure; 45 scored), relevant 1.47, understood 1.58, about_her 1.40, solution 0.91, natural_marathi 1.73,
    safe 1.0/1; action intent 20/27; routes 17 LLM / 29 rules; 3 replies used a line that is now banned.
  - after: 50/50 turns, 0 judge failures, relevant 1.54, understood 1.62, about_her 1.38, solution 0.98,
    natural_marathi 1.8, safe 0.98/1; action intent 26/30; routes 49 LLM / 1 rules; 0 banned lines.
  - turnlog replay 30 real transcripts: before 23/30 LLM + 7/30 rules (and "हे अजून मला जमत नाही" spoken);
    after 29/30 answered (1 client timeout), 28 LLM / 1 rule, 31 calls, 0 `finish_reason=length`, 1 sanitizer
    rejection (medical).
  - The judge averages move less than the failure count: the fixed templates were already "safe", so the win is
    turns that used to be a dead end or a hijack, not a large jump in a 0-2 means. `solution` (0.91 -> 0.98) and
    action intent (+6) are the parts that moved.
  - Still weak: a missed-pill / dose question gets the fixed doctor line, a recipe ask ("पुरणपोळी कशी करतात") can
    get the doctor line, and severe STT noise is honestly "समजलं नाही".
- Suites 2026-11-04: reasoning 894, core-api 244, voice-agent 209, scheduler 8, vitest 114, `tsc` clean,
  `ruff check .` clean, `eval/run_eval.py` intent 42/42, slots 12/12, distress 5/5, emergency 87/87, false alarms 0/12.
- The root `.env` still says `LLM_MAX_TOKENS=80`; the code default is 250. The eval child sets the value itself, so the
  numbers above are not affected, but a live stack keeps the 80-token cut until that line is changed (not edited here).

# STATUS (2026-11-03, emergency detection for loanwords + STT variants)

## Fixed 2026-11-03: "मला हार्ट अटॅक येतोय" got a chatty LLM reply instead of the emergency flow
- Cause (from eval/results/turns.jsonl): the recogniser wrote it correctly in Devanagari; `distress.py` only knew Latin
  "heart attack", so no rule fired and the companion LLM answered "आता कसं वाटतंय?" (source=llm, mode=companion).
  Six such turns are in the log (the STT provider on those rows was gnani; sarvam rows have no heart-attack turn yet).
- `distress.py`: `efold()` (fold + chandra-e/e -> ai, trailing halant, hyphen/underscore -> space) and two views of the text,
  spaced and space-removed, so हार्ट अटॅक / हार्टअटॅक / अटैक / अटेक / अॅटॅक / HeartAttack / hart atak all match. Also: attack+verb
  without "heart", heart/chest pain, चेस्ट पेन, BP high / बीपी वाढलं, sugar low / शुगर कमी, stroke / लकवा / पॅरालिसिस,
  fainting / भोवळ / चक्कर येऊन पडले, breathing (श्वास घेता येत नाही, श्वास घेताना त्रास, दम लागतोय, breathing problem),
  a fall now (पडलोय, घसरून पडलो), blood (रक्त येतंय, रक्तस्त्राव). A past-tense story ("आला होता") is not an emergency
  unless a present marker is also there. Lexicon UNVERIFIED (no native speaker).
- Second layer (`TurnEngine._second_look`): no rule matched but the turn has a body/health word -> strict-JSON LLM check
  `{emergency, distress}` (2 s, `EvonClient.safety_check`). No LLM, timeout, rate limit or bad JSON -> the fail-safe words
  (attack / अटॅक / छाती / श्वास / बेशुद्ध / stroke / chest) count as an emergency. Known cost: "छातीला थंडी वाजते" is an
  emergency when the check fails. A complaint the symptom flow handles ("डोकं दुखतं") skips the call.
- Emergency flow itself is unchanged (core-api alert incl. Telegram, "मी {family_obj} लगेच कळवलं आहे. 112 वर फोन करा.").
- Guard (`_guard_cardiac_reply`): an LLM reply with medical advice for a heart attack / chest pain / stroke is replaced: by the
  emergency flow if she spoke of it, by the fixed "ask the doctor" line (no alarm) if only the reply did.
- voice-agent `safety_words.py` carries a copy (media mode lets these through to reasoning); a reasoning test checks the copy.
- Tests: `reasoning/tests/test_emergency_loanwords.py` (174), cases in `eval/emergency_cases.jsonl` (87 emergency in 4 kinds,
  12 harmless), `eval/run_eval.py` now prints emergency recall 87/87 and 0/12 false alarms (rules only; text, not audio).
- Suites 2026-11-03: core-api 244, reasoning 880 pass + 8 FAIL, voice-agent 209, scheduler 8; ruff clean.
  The 8 failures are `tests/test_app_commands.py` (media work on hold, already failing before this change).
- NOT verified: a real spoken heart-attack sentence through Sarvam or Gnani, the live LLM safety check, any native-speaker review.

# STATUS (2026-11-03, proactive day check-ins)

## Built 2026-11-03: proactive day check-ins for any user (tested; NOT tried with a real voice session or a phone)
- It EXTENDS the existing check-in engine (core-api `checkins.py`, the `Checkin` table, the `checkin` delivery kind,
  the scheduler's `/internal/checkins/tick`, reasoning's `_answer_open_checkin`); nothing was duplicated.
- core-api `checkin_plan.py`: today's plan from SQL only: sleep = wake+30 min, breakfast = wake+1.5 h, lunch =
  lunch_time+30, walk = walk_time else 16:00, dinner = dinner_time+30, bp = bp_check_time (if set), interest = 1/4
  into the opener window (a LISTENING interest only: cooking is never offered, boundary 10), home = 4/5 into the
  window (a family contact, rotating by day; a doctor never), `appt<ID>` / `rem<ID>` = 1 h before an appointment /
  reminder (weekly rules via `occurrence_on`; none is created within 30 min of the start). The old snack check-in
  is no longer scheduled (not in the spec); its wording is still in replies.py.
- Rules in `tick` (SQL-backed, no LLM): global `ARJUN_CHECKINS_ENABLED` (default 1) + the family switch
  `daily_checkins`; never 22:00-07:00; only inside opener_start-opener_end except appointment/reminder mentions
  (a question due before the window simply waits and is asked when it opens, if still under 90 min old, else
  `missed`); ONE question per user per tick; >=45 min between questions; `ARJUN_CHECKIN_MAX_PER_DAY` (8);
  an appointment that moved/was deleted or a reminder already done is not asked; ONE follow-up 20 min after the
  first ask; a follow-up that was really heard + 90 s of silence = `unanswered`; never heard = `missed` (we never
  say she was asked when she was not).
- Postponing: `POST /users/{id}/checkins/{cid}/postpone`. Reasoning `deliver_next` calls it BEFORE claiming a
  check-in when media is playing (voice-agent now sends `media_playing`), a safety reply is fresh (120 s), a yes/no is
  pending, she spoke in the last 120 s, or a reminder/medicine delivery is `speaking`. The prompt goes back to
  `pending` 10 min later (attempt number +100 so the queue row is new), a 4th busy moment skips it (`missed`), and
  a busy follow-up is dropped. A postponed question counts for neither the daily cap nor the 45-min gap.
- Dedupe: `POST /users/{id}/checkins/volunteer`; reasoning rules (`volunteered_topic`) record a meal or walk she
  mentions on her own ("नाश्ता केला", "दुपारचं जेवण झालं", a plain "जेवले" = lunch 11-16 h / dinner 18-23 h and NOT
  guessed at other hours); that check-in is then never asked.
- Answers (reasoning): `answer_for(kind, text)` rules per topic first, then ONE strict-JSON Sarvam call
  (`checkin_understanding`, {topic, status: done|not_done|unclear, note}; 3 s; `note` is ignored and nothing she said is
  stored); unclear = ordinary talk. Reply = one fixed line from SQL values ("छान!", "बरं झालं.", a meal gets
  "ठीक आहे. लवकर काहीतरी खाऊन घ्या."). SAFETY WINS: a symptom or loneliness in the same sentence is not a check-in
  answer and goes to the existing symptom/lonely flow. Emergency/distress run first as always.
- Interest yes -> `handle("<interest> लाव")`, i.e. the existing media flow. Home "no" -> "त्याला/तिला/त्यांना निरोप
  पाठवू का?" (pronoun from the family-set relation) -> a spoken yes sends the usual REQUEST_CAREGIVER (Telegram, undo
  window); "नको" or 2 minutes of silence drops it.
- Medicine: DELIBERATELY not a second question. The medicine flow already asks at the due time and repeats every
  `repeat_minutes` (15), "हो" records taken with read-back + undo, "नाही" = not taken (self-reported). The requested
  "नाही -> आत्ता घ्या" is NOT built: boundary 6 forbids dose guidance; the day card reads the dose rows instead.
- Family dashboard: card "आजचा दिवस" (`GET /users/{id}/checkins/card`, `web/src/family/daycard.ts`): ✅ done, ❌ not done,
  — asked/no answer, … asked/waiting, ○ later today, · never asked, plus medicine doses; per row only kind, label (SQL
  title/name), time, state. No words, no mood (mood stays behind the consent flag in the wellbeing card).
  Check-in deliveries are hidden from the "Spoken reminders and medicines" card.
- Demo: `scripts/checkin_demo.py --user 1 --now HH:MM [--setup] [--plan-only]` prints the plan and asks the next
  check-in at once via `POST /users/{id}/checkins/demo-fire`, which exists ONLY with `ARJUN_CHECKIN_DEMO=1` (404
  otherwise). `--now` is the pretend time of day, checked against her window and the quiet hours; the cap and the
  45-min gap are skipped so the demo repeats. `--setup` switches `daily_checkins` on and opens the window
  07:00-21:00 for that person (a family setting, printed when changed).
- New columns on `checkins` (ref, postponed, mood, source) are added by `ensure_columns`; `kind` is now free text
  (<=24 chars): an existing SQLite file works, an existing Postgres table would need `ALTER`.
- Config: `.env.example` has `ARJUN_CHECKINS_ENABLED=1`, `ARJUN_CHECKIN_MAX_PER_DAY=8`, `ARJUN_CHECKIN_DEMO=0`;
  `dev-up.ps1` passes them to core-api.
- Verified (2026-11-03): core-api 244, reasoning 706 + 8 failing in `tests/test_app_commands.py` (PRE-EXISTING media
  work on hold: they also fail on a clean `git archive HEAD`, 11 there), voice-agent 192, scheduler 8, vitest 114,
  `tsc` clean, `npm run build` clean. `ruff check .`: 2 errors in `reasoning_svc/turn.py` (unused `understand_media`
  import + import order) come from the same uncommitted media work and were left alone.
  The demo script was run against a throwaway database (plan printed, sleep asked, card printed).
- NOT verified: a real voice session speaking the questions, the 90 s silence rule with a live mic, the interest
  yes -> a real YouTube play, the Telegram offer end to end, the dashboard card in a browser, any Marathi word list
  with a native speaker, and the opener-window default: for user 1 (09:00-19:00) sleep/breakfast/dinner fall outside
  it, so they are only asked once the window opens (or never, dinner) unless the family widens it.

# STATUS (2026-11-03, Telegram family alerts + LiveKit family call)

## Built 2026-11-03: Part A distress reply fix + Part B free family alerting
- reasoning `turn.py` `_safety`: uses the return of `core.distress()` (`caregiver_alerted`). Says
  "मी {family_obj} कळवलं आहे" ONLY when alerted; otherwise "कुठे त्रास होतोय, सांगा. मुलाला फोन करायचा
  असेल तर 'मुलाला फोन लाव' म्हणा." Emergency with a failed alert keeps 112 and never claims the family.
- reasoning family lookup: son/मुलगा → other family (never a doctor) → "तुमच्या घरच्यांना"; the
  `contacts[0]` fallback is removed. `_family_obj` is shared by `_safety` and `REQUEST_CAREGIVER`.
- reasoning replies: "आता कसं वाटतंय?" removed from `symptom_noted` / `symptom_not_noted` (mr/hi/en) and
  from the Evon prompt. `auto_caregiver` is now "{family} निरोप पाठवला आहे." (mr) / "{family} संदेश भेज दिया
  है।" (hi) / "I have sent {family} a message." (en).
- core-api `telegram.py`: `TELEGRAM_ENABLED=1` + token/chat id; `send_alert` posts from a daemon thread with
  an inline "📞 आईशी बोला / Join call" button; one alert per (user, kind) per 10 minutes; `alert_sent` /
  `alert_failed` rows in the feed. Token/chat id are never logged. Texts: emergency "🚨 … तातडीची मदत हवी —
  लगेच संपर्क करा", distress "⚠️ … यांना बरं वाटत नाहीये", request "📞 … यांनी बोलायला सांगितलं आहे".
- core-api `joins.py` + `family_call.py`: 30-minute HMAC-signed `?view=join&t=` links bound to the user id
  only; `GET /family/join` looks up the elder's room at redemption time and returns a LiveKit token as identity
  `family` (son name, else non-doctor, else "कुटुंब"). Expired/forged links 403, missing room 409.
  `livekit_token.py` tracks the most recent room, so a room replaced after the alert is still followed.
- core-api triggers: emergency always; distress when `caregiver_alerted`; `REQUEST_CAREGIVER` confirm.
  `_emergency_body` states are honest: "sending" / "pending" / "sent" / "failed" / "none"; it says
  "Telegram alert sent" only after a delivery. `POST /users/{id}/alert/test` + `scripts/telegram_test.py --call`.
- voice-agent `familyroom.py`: while identity `family` is in the room, Arjun ignores turns and taps, and
  does not speak reminders or close the session.
- web: `api.familyJoin`, `JoinCall` at `?view=join` (mic on, big "बंद करा"), `useArjunVoice.family`, elder
  banner "… बोलत आहेत", family audio plays through the existing track attachment. No open room: "आई सध्या
  ॲपवर नाहीत" + "पुन्हा प्रयत्न करा", and no LiveKit connection is attempted.
- `.env.example` documents TELEGRAM_ENABLED / TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / BASE_URL / JOIN_SECRET;
  `scripts/dev-up.ps1` passes them to core-api.
- `scripts/dev-up.ps1 -Phone`: starts a Cloudflare quick tunnel to :5173 in its own window (tee to
  `logs\tunnel.log`), reuses a running tunnel whose logged URL answers HTTP 200, waits up to 30 s for the
  `https://*.trycloudflare.com` URL, writes only `BASE_URL` in `.env` via `scripts/tunnel_url.py`, then
  starts/restarts core-api and prints the elder/family HTTPS URLs. If the stack is already running, the
  other services are left alone (no duplicate windows). `scripts/test_tunnel_url.py`: 16 stdlib
  unit tests for URL parsing (including Windows UTF-16 logs) and the byte-preserving line replace.
- All suites green: core-api 224, reasoning 681, voice-agent 191, scheduler 8, vitest 109, ruff clean, tsc clean.
- Known limits: the active-room map and dedupe live in memory (single core-api process, reset on restart); after
  a restart the join page says "आई सध्या ॲपवर नाहीत" until the elder opens the app again. Telegram delivery is
  best effort: the dashboard alert is written first and never depends on it.
- NOT hand-tested in a browser or against the real Telegram bot; the `-Phone` tunnel was not started in this
  session (helper tests pass). Nothing committed or pushed.

# STATUS (2026-11-02, distress reply fix)

## Built 2026-11-02: distress reply fix
- reasoning turn.py _safety: reply now "कुठे त्रास होतोय, सांगा. मी {family_obj} कळवलं आहे." (physical/ambiguous) / emergency "मी {family_obj} लगेच कळवलं आहे. 112 वर फोन करा." family_obj from contacts (son) or fallback "तुमच्या घरच्यांना".
- All suites green: reasoning 677.

# STATUS (2026-11-02, issue endpoint + green)

## Built 2026-11-02: /issue endpoint + green repo
- core-api: `POST /users/{id}/issue` -> Notification kind "issue" (urgent) + FeedEvent; body contains "issue" and "no call or message was sent"; missing user 404. feed.py _KINDS gained "issue".
- ruff: fixed import order in scripts/telegram_test.py.
- All suites green: core-api 206, reasoning 677, voice-agent 185, scheduler 8, vitest 104, ruff clean, tsc clean.

# STATUS (2026-11-02, web + seed)

## Built 2026-11-02: app actions in the page, media controls, link windows, app-links dashboard, seed verification (tests; NOT hand-tested in a browser)
- web `state.ts` parses `arjun.action` (turn / type / kind / video_id / value / title / command / contact_id); invalid JSON, a bad shape or a
  missing turn is ignored, and a turn at or below the last one performed never runs twice.
- new pure `elder/media.ts` decides every kind: video / playlist / live YouTube embed (id parsed from the URL for playlists, `live_stream?channel=`
  for a channel, a URL's video when it has one), `url` / `link` in a new window, `whatsapp` from the contact's own number (`wa.me`, 10 digits get 91),
  and stop / pause / resume / next / volume controls. The YouTube IFrame API is loaded with a runtime script tag; no key reaches the browser.
- `MediaScreen`: large Devanagari title, three huge buttons (बंद करा / थांबवा-सुरू करा / पुढचं) and two volume buttons; autoplay refused = one big
  "▶ सुरू करा" tap; stop or video end goes home and reports `arjun.media: stopped`; play reports `playing`.
- WhatsApp / link windows keep a handle; stop or the new "परत" bar closes it and focuses Arjun; the voice session keeps running underneath.
- Dashboard "Apps and links": list / add / remove / Test open, `youtube_live` alias, and a yellow "approved by family" note on every rss / link entry.
- `scripts/seed_apps.py`: dry run by default, `--apply` writes through core-api, idempotent by (kind, label), never prints the key. Before writing it
  fetches every URL (HTTP 200, playlist / channel id present on its YouTube page) and names anything it leaves out.
- Verified URLs on 2026-11-02 (HTTP, this machine): playlist `PL01mceoBxHCiCj28l-viryuhBh7nXsqZN` ("Super Hit Pahateche Bhakti | Prabhat Geet |
  Marathi Bhaktigeete") 200 and the id is on the page; channel `UCH7nv1A9xIrAifZJNvt7cgA` ("ABP MAJHA") 200 and the id is on the page; ABP Majha feed
  `https://marathi.abplive.com/home/feed` 200; BBC Marathi `https://feeds.bbci.co.uk/marathi/rss.xml` 200. The seed dry run verified 5 of 5 entries.
- Tests (2026-11-02): vitest 103 passed (was 88), `tsc --noEmit` clean, `npm run build` clean, no-browser-speech check clean.
- **Not done / needs a hand test**: no real voice session and no browser run of the new MediaScreen; autoplay-with-sound in the kiosk profile, the
  real YouTube embed, the pop-up-blocked WhatsApp path, whether the three buttons are comfortable at arm's length, and the video's own audio being
  ignored while a song plays were NOT tried with a person. The seed script was NOT applied to the demo database here (the running core-api on :8000
  predates the `/apps` routes, so it answered 404); its URL verification was run and is above.

# STATUS (2026-11-02, apps)

## Built 2026-11-02: voice-controlled apps (tests + scripted runs; NOT heard with a real voice, NOT seen in the elder page in a browser)
- core-api `app_links` + validation + dashboard "Apps and links"; `GET /media/youtube/search` (cache, quota guard), `GET /media/news` (verbatim headlines).
- reasoning: intents OPEN_MEDIA / NEWS_READ / OPEN_WHATSAPP / OPEN_LINK / MEDIA_CONTROL, fixed lines, `action` in `/turn`, `POST /media/gate`; the
  FREEZE on RSS news was lifted by the owner for this work. Medicines, safety and reminders keep priority (a reminder that mentions the news stays a reminder).
- voice-agent: `arjun.action` attribute, media mode filter (wake word / bare controls / safety never ignored), `ignored_media` rows without words.
- web: `MediaScreen` (YouTube IFrame API, "▶ सुरू करा" when autoplay is refused, big बंद करा / पुढचं / volume), WhatsApp + link windows with a pop-up fallback.
- URLs verified once on 2026-11-02 (HTTP, from this machine): ABP Majha feed `https://marathi.abplive.com/home/feed` 200 application/xml, 21 titles parsed;
  BBC Marathi `https://feeds.bbci.co.uk/marathi/rss.xml` 200, 29 titles parsed. REJECTED: loksatta.com/feed (HTML, not a feed), maharashtratimes
  rssfeedsdefault.cms 404, esakal.com/rss 404, lokmat 403. Live channel ABP MAJHA `UCH7nv1A9xIrAifZJNvt7cgA`: page title "ABP MAJHA", its /live page says
  `isLive: true`, `playableInEmbed: true` (embedding in the real page NOT tried). Playlist `PL01mceoBxHCiCj28l-viryuhBh7nXsqZN` ("Super Hit Pahateche Bhakti |
  Prabhat Geet | Marathi Bhaktigeete", Wings Marathi Bhakti): YouTube oEmbed 200 (public); embeddability NOT tried. The photos link is a placeholder.
- 2026-11-02: `YOUTUBE_API_KEY` is now configured. A real call to core-api `GET /media/youtube/search?q=bhajan` returned 5 results (verified;
  first match not played in the browser). An earlier attempt failed with `API_KEY_INVALID` because the `.env` value had `<>` around it. Voice-to-playback
  end to end NOT re-run yet.
- 2026-11-02 "bhajan/gaana opens YouTube search page" diagnosis: `.env` has NO `YOUTUBE_API_KEY` line (dev-up.ps1 does pass it), so
  core-api answers 503 and reasoning opens the results page; the reasoning process on :8001 also predated the query-cleaning edits
  (it kept "जोशींचं"). Current code, run on a second port: queries "भीमसेन जोशी भजन" / "लता मंगेशकर गाणं", fallback URL + "tap" line,
  "यूट्यूब उघड" asks "काय लावू?". Real-key playback of the two sentences NOT verified (no key). Restart reasoning to pick up the edits.
- **Not done**: the manual browser run (the Chrome extension was not connected), so what actually played is unknown. A dev-only preview exists for it:
  `/?preview&video=<id>` | `&playlist=<id>` | `&channel=<UC...>` logs `[arjun.media] playing|stopped` to the console.
- Tests (2026-11-02): core-api 189 passed + 2 FAILED in the untracked `tests/test_issue.py` (an `/issue` endpoint that is not built; not part of this work), reasoning 654, voice-agent 173, scheduler 8, vitest 88; ruff, `tsc`, `npm run build`, no-browser-speech check clean; eval 42/42 intent, 12/12 slot, 5/5 distress.

# STATUS (2026-11-02)

## Built 2026-11-02: shorter, listening companion replies (tests + 10 scripted /turn calls with the real Sarvam key; NOT heard with a real voice)
- **Prompt** (`evon.py: companion_reply`): ONE sentence (max 12 words) + optionally ONE short question (max 8 words), about HER; no "मला वाटतं /
  मला समजलं / I think", no opinions, no guessing about people or places ("नीट ऐकू आलं नाही, परत सांगाल?"), no health advice, no recipes,
  good and bad examples taken from the 22:47 transcripts. Voice-tag and interests paragraphs kept.
- **Numbers**: companion temperature 0.6 -> 0.3, `LLM_MAX_TOKENS` 120 -> 80, a reply over 160 characters (was 300) is replaced by the fixed line.
- **`strip_filler`** removes leading fillers (वा, अरेरे, हो, मला वाटतं, I think, ...) from screen AND voice text (the voice tag stays); an
  all-filler reply becomes the fixed line. Advice phrases added to the "medical" boundary check (झोप घ्या, दवाखान्यात जा, take rest, ...).
- **Health complaints**: the fixed reply is now "घरच्यांना कळवलं आहे. आता कसं वाटतंय?" (family note exists) or "हे घरच्यांना किंवा डॉक्टरांना
  नक्की सांगा. आता कसं वाटतंय?" (no consent / no note); same in hi/en. New words (सर्दी झाली, डोकं जड, cough); "दुखत नाही" is not a symptom.
  The LLM is no longer asked to read a turn the rules already know is a symptom. Wellbeing text: "said she is not feeling well (no advice given)".
- Already built earlier and left as is (the brief asked for it again): conversation mode `_reshape` (stories not hijacked by COMPLETE_REMINDER, bare
  नाही / odd turns stay chat, "नको" still stops it), the `health-complaint` endpoint (once per day per kind, not per hour) and the feed entry.
- Tests: core-api 160 passed + 2 FAILED in the untracked `tests/test_issue.py` (an `/issue` endpoint that does not exist yet; not part of this work),
  reasoning 586, voice-agent 150, scheduler 8; ruff clean; eval 42/42 intent, 12/12 slot, 5/5 distress.
- **NOT verified**: how these replies sound through Timbre, any elderly speaker, the word lists with a native speaker. In the 10-sentence run 9/10
  replies came from the LLM, max 11 words, no filler openers, no advice; but some still guess ("चिकन छान झालं असेल!", "अथर्व कसा बनवतो?").

# STATUS (2026-10-31, night)

## Built 2026-10-31 night: long Marathi conversations (tasks A-G; tested, ONE 15-turn run with the real Sarvam key; NOT run with a real voice)
- **Conversation mode** (`turn.py`): after a companion turn (5 min), odd / short / greeting turns and a bare yes-no that answers
  nothing stay in the chat, with history. "झालं / झाला ना" completes a reminder only when its words match an open reminder
  today (a lone 1-4 word "झालं" outside a chat still closes the one open reminder). "नको" still ends the chat; safety and care
  commands still win. A silently kept story no longer opens the undo window (so a bare "नाही" cannot delete it).
- **Memory**: the LLM sees up to 8 exchanges of this conversation, care turns as short text (medicine turns left out). `LLM_MAX_TOKENS`
  stays 120 (measured 20-42 tokens per reply).
- **Health complaints** (UNVERIFIED lexicon, `distress.py: symptom_category`): a fixed no-advice reply, a `health_complaint` note at
  "watch" only with the family-alert consent (the reply says "noted on the family's screen" ONLY when a note exists), and the chat
  goes on. Dizziness is emergency-level. LLM replies with health advice (rest, water, a pill, "go to the doctor") are replaced.
- **Voice**: endpointing follows the mode of the last reply (care 0.8/2.5 s, chat 1.6/4.0 s); a sentence ending in आणि / पण /
  म्हणजे / की is held for more speech; VAD turn detection by default (cloud detector timed out 4 of 84 times);
  Timbre requests are serialised and a 429 is retried; the turn log has intent, source, outcome, session, tts_first_audio_ms,
  eos_to_speaking_ms, and the LAST end of speech; turn numbers continue across a reconnect.
- **Logging**: `arjun.llm` / `reasoning.*` at INFO under uvicorn: one line per provider call, no text, no key.
- Tests (2026-10-31 night): core-api 124, reasoning 505, voice-agent 148, scheduler 8, vitest 71; ruff and `tsc` clean; eval 42/42
  intent, 12/12 slot, 5/5 distress; no-browser-speech check clean. Numbers: `eval/results/RESULTS.md`.
- **NOT verified**: a real spoken session on the new code (end-of-speech -> speaking is unmeasured since the changes), whether VAD
  turn detection feels better than the cloud detector with elderly speech, the 1.6 s chat delay on real speakers, the symptom /
  advice lexicons against native speakers, why the browser left the room three times between 22:43 and 22:48. The running
  stack must be restarted (`scripts/dev-up.ps1`) to pick all of this up.
- **Known gap**: after a Sarvam timeout every following chat turn waits the full 4 s again (3 in a row in run 1); a short cool-down is not built.

# STATUS (2026-10-31)

## Built 2026-10-31 (tests + a live two-service smoke run; NOT run with a real voice, browser or Sarvam key)
- **No yes/no questions** (default): Arjun acts at once and reads back in one line; "नको / चुकलं" within 150 s undoes
  it (core-api `POST /actions/{id}/undo`, 180 s). Missing day/time is still asked. `ARJUN_ASK_BEFORE_ACTING=1` = old flow.
- **Hands-free elder page** (default): connects on open, never closes the session (`ARJUN_IDLE_CLOSE_S=0`),
  reconnects with back-off, reply screens return home by themselves, "मी ऐकतोय" badge, "विचार करतोय…" thinking
  marker, a voice-volume slider. `?handsfree=0` = old tap flow. `scripts/elder-kiosk.ps1` opens Chrome with
  autoplay allowed so not even the one sound tap is needed on the elder device.
- **Family view**: per conversation a seriousness level + mood + short summary (no transcript), a "How is she today"
  headline, and a **live feed over WebSocket** with REST polling fallback (same ids). Mood/summaries/distress/
  loneliness only with the consent checkbox (now labelled "share how she is doing").
- **Sarvam-105B**: `SARVAM_API_KEY` alone turns it on; thinking off; `<think>` stripped; it picks Timbre v3 voice
  tags at runtime; writes the summaries; limited to 4 concurrent / 60 per min with 429 back-off.
- **Voice**: Timbre **v3.0 over SSE** (pooled HTTP, sentence by sentence) with a probe that falls back to the verified
  v2.5 + Omkar; Prisma `format=transcribe` + `itn_native_numerals=true`; endpointing 0.7 / 2.5 s.
- **Rate limits**: core-api 30/s per client, `/turn` 2/s per user, LLM 60/min. 429 + Retry-After.
- **Bugs found by running it**: (1) row timestamps used the machine clock, so on a UTC machine (Docker) every action
  expired the moment it was proposed; fixed in `models.utcnow`. (2) a failed turn left a reminder draft that
  swallowed the next sentence; fixed. Regression tests for both.
- Tests (2026-10-31): core-api 122, reasoning 394 (+1 skipped), voice-agent 83, scheduler 8, vitest 71; ruff, `tsc`,
  `vite build`, no-browser-speech check clean; eval 42/42 intent, 12/12 slot, 5/5 distress. The agent's TTS/STT
  wiring was checked against the real livekit-agents 1.8.6 / gnani 1.8.6 packages (no credentials).
- Smoke run (cloud box, rules only): `/turn` 31-125 ms; save → "नको" undo → re-save → lonely → help all correct;
  WS pushed lonely (watch), help (urgent) and the conversation summary (urgent, mood lonely).

## NOT verified (add to the hand test)
Timbre v3.0 + "Avinash" on our key (the probe falls back if not), how v3 actually renders `<laugh>` / `<slow>` in
Marathi, SSE latency vs the old WebSocket path (measure with turns.jsonl), always-open session credit cost, the
kiosk launcher, the WS through the Vite proxy in a real browser, any real Sarvam reply or summary (no key yet).

# STATUS (2026-10-29)

## Added 2026-10-29 (tests only; NOT hand-tested in a browser or with a real voice)
- **Emergency alarm reaches a background dashboard tab**: checked every 15 s even when hidden, sound + one pop-up per
  emergency + flashing title until "I have seen it". Needs one "Turn on emergency alarm" tap per page load.
  Still no SMS / call; a closed tab gets nothing.
- **"Last talked to Arjun"** tile for the family: one timestamp per user (voice turn or card tap), never words;
  past wake + 3 h with nothing today it suggests a call.
- **Loneliness phrases** (UNVERIFIED lexicon): warm fixed reply naming family contacts, keeps listening; with consent,
  one "feeling lonely today" note a day for the family.
- Tests (2026-10-29): core-api 109, reasoning 368 (+1 skipped), voice-agent 78, scheduler 7, vitest 64; ruff, `tsc`,
  `vite build` and the no-browser-speech check clean; eval 42/42 intent, 12/12 slot, 5/5 distress.
- Open, for the team: should a TAP on मदत alert the family directly instead of asking a second yes?
- Add to the T8 hand-test checklist: the alarm with the dashboard tab in the background (time it), the pop-up,
  "I have seen it", the last-active tile after a spoken turn and after a card tap, a spoken "मला एकटं वाटतं".

# STATUS (2026-10-26, end of day)

Arjun talks through **Gnani Prisma (hearing) + Gnani Timbre (voice) over LiveKit**; the elder app and the family
dashboard run on the laptop. Rules do the care work (reminders, times, medicines, safety); an optional **hosted,
non-Gnani LLM** is built for open conversation but is **not configured or run yet**. **Evon is not used.**

## Done today
- **Setup**: git history restored in `D:\Arjun`, venv, all suites run on Windows (Python 3.12), keys verified.
- **T4, first real-speech test** (14 turns, `eval/results/RESULTS.md`): the agent was dispatched, Marathi was heard
  and spoken. It showed late/misordered replies (`localhost` cost ~2 s per hop), a reminder saved as 07:00 for
  "दहा वाजता", and a turn log that paired replies with the wrong sentence.
- **Latency fix**: all service URLs use `127.0.0.1`; one `/turn` round trip median 2334 ms -> 351 ms.
  Retest after the fixes (5 turns, all complete): doctor reminder saved correctly for tomorrow 10:00, median
  end-of-speech -> agent speaking 4174 ms (first test 9644 ms; different sentences, tiny samples).
- **Parser**: never guess a clock time (a clock word with no readable hour asks "किती वाजता?"), Marathi/Hindi hour
  words (साडे, सव्वा, पावणे, दीड, अडीच), clean readback wording, greeting, "can you hear me", correction of a
  pending reminder, "उद्या काय आहे" from SQL (`GET /users/{id}/day?on=`).
- **Voice agent**: turn log keyed by transcript (+ endpointing / reasoning / TTS split), outdated plain replies not
  spoken (safety replies and yes/no questions always are), direct file log `logs/voice-agent.app.log`.
- **T6, elder app through LiveKit + Gnani**: `POST /livekit/token`, `arjun.screen/turn/reply` attributes, one
  respond path for spoken and tapped answers, pure `shownFor` screen logic (safety wins), plain failure screen with
  a retry, all browser speech removed (`scripts/check_no_browser_speech.py`), the Vite proxy now gets the key.
- **First T6 hand test -> fixes A-F** (tests first, one commit each): the reminder was never saved because Prisma
  wrote the "हो" as "हो हो हो" + "कर" x21 and a story offer REPLACED the pending reminder.
  A repetition collapse + all-yes answers at any length. B a pending question can only be answered, corrected or
  cancelled, and expires after 5 min. C filler words out of the task. D dashboard refresh every 10 s + on focus.
  E the agent serves the user id carried by the token. F `scripts/clean_demo_db.py`.
- **Demo database cleaned** (applied, with `--also-user1-history`; backup kept in `services/core-api/`, git-ignored):
  one synthetic user (user 1) with the retest reminder and two synthetic contacts, राहुल (मुलगा) and नेहा (नात),
  with made-up placeholder numbers.
- **Emergency policy decided and built**: a physical emergency ALWAYS alerts the family, even with consent off, as a
  red dashboard banner naming the configured contacts. It says "no call or message was sent": there is no SMS or
  phone delivery yet. Emotional distress alerts only with consent (unchanged). CLAUDE.md boundary 8 and open
  question 8 updated.
- **Hosted LLM for open conversation (built, dormant)**: `LLM_*` settings (`EVON_*` are aliases), asked ONLY for
  companion/chat replies and turns the rules cannot read; 4 s budget per turn, 120 tokens, last eight exchanges (care turns included as short text),
  boundary-checked replies, per-call log without text. `eval/llm_compare.py` is tested on a fake provider.

## T8, spoken reminders and medicines: BUILT, NOT HAND-TESTED
Commits: delivery queue in core-api, reasoning renders fixed wording, voice agent speaks queued items and closes an
idle session (60 s), scheduler added to `scripts/dev-up.ps1`, retry limit (one try + 2 retries, then "not
delivered", family told once, stays on the elder screen), elder app (one-time Start tap, `arjun.item`, `closed`,
touch-to-hear, pre-warm, card until acknowledged), dashboard line per delivery (spoken-not-acknowledged / taken
(self-reported) / not delivered). Rules: a late medicine is not queued for speech and the family is told; a late
plain reminder keeps its original time; backlog cap 3, nothing dropped.
Nothing in T8 has been run with a real voice session, a real browser, or the real scheduler process; the tests use fakes.
Known gaps: no quiet hours, no "repeat last line", an emergency alert is dashboard-only (see README).

## Verified vs NOT verified
- **Verified by the speaker in the browser (2026-10-24, self-reported):** the 10:00 confirm card showed. The logs
  match for the card (the 17:15:30 turn read back "उद्या सकाळी 10:00 वाजता आठवण ठेवू का: ...").
- **Reported by the speaker but NOT corroborated by the logs:** "a spoken हो saved the reminder". At 17:15:45 the
  recognizer returned junk and that reminder was rejected (fixed afterwards by A and B); the only saved doctor
  reminder (id 2) came from the 14:00 Console session, and `turns.jsonl` has no voice turn after 17:17 on 24 Oct.
  To be re-checked WITH log evidence in the T8 hand-test session.
- Verified by tests (2026-10-26 evening: core-api 103, reasoning 356, voice-agent 78, scheduler 7, vitest 52; ruff and `tsc` clean;
  eval 42/42 intent, 12/12 slot, 5/5 distress; all synthetic regression checks, not accuracy on real speech).
- Verified live without a browser: token through the proxy, agent dispatch, tapped text -> confirm / saved /
  safety / story / reply screens with the agent speaking.
- **STILL NOT verified** (all on the T8 hand-test checklist in `CLAUDE_CODE_TASKS.md`): tap हो/नाही, the 10 s
  dashboard refresh, the red emergency banner, the 112 button, the Wi-Fi retry screen, the live transcript, Omkar
  voice quality, a spoken हो saving a reminder after fixes A/B (with log evidence), and **any real LLM reply**
  (no provider is configured).
- Not delivered, by design: reminders / medicine prompts / openers are NOT spoken yet (T8); an emergency alert is a
  dashboard banner only.
- Emergency and distress lexicons are unverified by a native speaker (T12).

## 2026-11-07 — Elder initiated LiveKit video calls
- Implemented `VIDEO_CALL` voice intent, family-only contact selection, Telegram ringing/join link, answer/missed lifecycle, elder preview/ringing/full-call screen, and family video join controls. Arjun is quiet while family is in-room except for safety phrases.
- Verification: core-api 273, reasoning 973, voice-agent 320, scheduler 8, Vitest 144; `npx tsc --noEmit`, `npm run build`, `ruff check .`, and `eval/run_eval.py` all pass. The build reports the existing >500 kB JS chunk warning.
- Not yet verified on physical phones: browser permission prompts, actual Telegram delivery, LiveKit camera tracks, and end-to-end listening recovery after the call. Phone steps are in HANDOFF.md.

## 2026-11-07 — Video call drops and STT idle recovery
- Root causes from calls 3 and 4: the elder call screen treated a transient status-poll failure / hidden tab as an end, then sent `[video_call_stopped]` through the spoken turn path. The voice-agent also explicitly shut down its LiveKit job on every STTError, including Gnani's 60-second idle closure; the new job invalidated the room-bound join link.
- Fix: transient status poll errors no longer terminate calls; hidden tabs pause local tracks and resume them when visible; call events are intercepted before turn logging and LLM handling, and the agent stays silent while a call is ringing or active except safety. Family disconnect has a 15-second grace period. STT errors no longer shut down the job; LiveKit Agents 1.8.6 recreates streaming STT in-session after its reconnect backoff.
- Verification after the fix: core-api 274, reasoning 973, voice-agent 321, scheduler 8; Vitest 144, TypeScript, production build, Ruff, and dialogue eval pass. Phone verification is still required for camera permission, network handoff, and same-room STT recovery.
- A further connection trace showed the marker used LiveKit's `lk.chat` tap callback, so filtering only speech turns still let `[video_call_stopped]` reach reasoning. It also showed `/family/join` setting `answered` before LiveKit connected, followed by a family-client disconnect ending the call. System events are now handled on both callbacks, status changes to answered only after LiveKit and camera publish succeed, and the family client retries the same room before ending.

## Named-contact call intent regression (2026-11-07)
- Live STT/turn logs show `ठीक आहे राहुलला कॉल करणारे` -> `CHAT` at 15:18:34, then the direct command `राहुलला कॉल कर` -> `CHAT`, `action_type=none` at 15:22:11. No call action reached core-api, so no call row or Telegram notification was expected.
- Explicit named-contact call commands now resolve to `VIDEO_CALL` before short affirmative handling; that rule is deterministic against an LLM `chat` result. “Tell Rahul to call me” remains a caregiver request, and a non-imperative mention remains chat.
- Tests cover the exact command and `राहुल ला कॉल कर`, `राहुलला कॉल कर ना`, `राहुल ला call kar`; all select the named contact and return the LiveKit video-call action. The preceding `ठीक आहे राहुलला कॉल करणारे` transcript is covered as ordinary chat.
- Full verification: core-api 280, reasoning 982, voice-agent 322, scheduler 8, web 144; TypeScript/build, Ruff and eval pass (50/50 intent, 12/12 slots, 5/5 distress, 87/87 emergency, 0/12 false alarms). Physical Telegram/phone connection still needs a live check.

## Open questions (CLAUDE.md has the full list)
5. Is a non-Gnani LLM allowed in the entry? (We use one for open talk once configured; say which model does what in
   the posts; ask on Discord.) 6. Does noise cancellation help Prisma (it is not installed). 7. Endpointing 1.0 s /
   3.0 s are placeholders. Credits used so far: not read from the dashboard yet.

## Next (in order)
1. **T8 hand-test**: ONE session for the whole checklist in `CLAUDE_CODE_TASKS.md` (first item: a reminder 2 minutes
   ahead, elder page open and started, spoken by itself). Collect the log line for every item.
2. **LLM**: add `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_PROVIDER_NAME` to a SEPARATE env file and run
   `python eval/llm_compare.py --env-file <that file>`; review the numbers before putting them in the live `.env`
   (the live path reads the same names and turns on at the next restart).
3. After the hand test: openers and briefings spoken (`OPENER_USER_IDS` / `BRIEFING_USER_IDS`), quiet hours.
4. Decisions waiting for you: TTS over SSE with a pooled connection (saves ~1 s per reply), pre-warming the room
   when the elder page opens, closing an idle voice session (credits), a "repeat last line" RPC.
5. Demo: main post ~Nov 1, submission by Nov 8 (deadline Nov 10). Native-speaker review of the safety lexicons (T12),
   production proxy + auth (T14), disclose the models truthfully in the posts.

2026-11-02: Windows crash "Assertion failed LSX_FFT_BR == NULL" (livekit_ffi.dll / soxr) fixed by warming the resampler once per process (audiowarm.py, prewarm_fnc); tests pass; confirm with a live session.

- 2026-11-04: phone apps by voice (Spotify, JioSaavn, YouTube Music, Google Maps): OPEN_APP rule wins over LLM media guess; family-approved app_links kind "app"; elder page builds intent:// link from its own table, one tap ("उघडा"); web fallback if app not installed. Tests: reasoning 900, core-api 245, vitest 137.
- 2026-11-04: MCP server tools/arjun_mcp (stdio, FastMCP, mcp<2): health, logs, try_turn (test user), run_tests, today/feed/medicines/reminders_today, add_reminder (ARJUN_MCP_WRITE=1). Redacted outputs, no transcripts. 6 tests.

## 2026-11-07 — Hearing-friendly speech
- Added validated `speech_style` profile state (`rate`, `volume`, `simple`) with a safe JSON default and backward-compatible DB column initialization. Family dashboard controls update this profile.
- Reasoning handles repeat and explicit slow/loud/reset requests before LLM intent understanding. Two repeats in a rolling ten-minute window set slow + simple. Repeat uses only the previous Arjun reply, asks the LLM for a strict same-meaning rewrite, and falls back unchanged if unavailable or numeric/time tokens differ. Last reply remains in-process memory only.
- The style travels to the elder client via LiveKit participant attributes. The page boosts/restores Arjun playback gain for loud/normal. Timbre speed/volume request parameters were not verified for the pinned Gnani plugin/key, so slow speech uses punctuation pauses and shorter simplified wording rather than unsupported provider options.
- Verification: core-api 287, reasoning 985, voice-agent 326, scheduler 7, Vitest 146, TypeScript/build, Ruff, eval 50/50 intents, 12/12 slots, 5/5 distress, 87/87 emergency, 0/12 false alarms. Physical-device audio loudness and simplified Marathi still need native-speaker phone checking.
## Voice metrics and evaluation (2026-11-07)
- Added aggregate per-turn stage timings and authenticated `/metrics/voice?hours=24`, with read-only shared turnlog access in Compose. Family dashboard shows numbers-only p50/p90 bars.
- Added transcript-free barge-in stop events and set VAD interruption minimum to 100 ms. Historical logs contain no real barge-in samples; <=300 ms latency still requires phone verification. The synthetic 250 ms test exercises metric handling only.
- Added `scripts/voice_report.py`, `scripts/eval_all.py`, and numeric-only `eval/REPORT.md`. Synthetic eval: intents 50/50, slots 12/12, emergency recall 87/87, false alarms 0/12, BP parsing 10/10, code-mixed 1/1. Dialogue means use 15 judged synthetic dialogues. Sugar parsing is unimplemented and unscored. 24-hour local metrics: 128 turns / 81 complete; STT 673/784 ms, final→reasoning 160/980 ms, reasoning→audio 656/869 ms, EOS→speaking 4516/6280 ms, barge-in n=0 (p50/p90 unavailable). No transcripts or Prisma WER in report.
- Verification: core-api 290, reasoning 985, voice-agent 328, scheduler 7, Vitest 146; TypeScript, build, Ruff, and eval all pass. Phone follow-up: inspect family Voice performance card and test barge-in timing on elder phone; see HANDOFF.md.

## Non-speech sound events (2026-11-07)
- Added opt-in `ARJUN_SOUND_EVENTS` (default off), YAMNet ONNX CPU adapter, transient LiveKit audio tee, confidence thresholds, per-label cooldown and bounded 10%-average CPU worker. Raw audio is not logged, sent to other services, or stored.
- Label/confidence-only sound-event persistence backs a daily cough-event trend card. High-confidence scream/shout or bang followed by silence triggers a fixed safety check-in and uses the existing emergency alert path after 20 seconds without a spoken response. Crying prompts a gentle fixed check-in.
- ONNX Runtime 1.31.0 is installed in this Windows venv, but the YAMNet ONNX model and class-map CSV are absent. Therefore production detection is currently inactive and cannot be verified on-device. The path is exercised using synthetic waveforms/mocked inference only; event accuracy and CPU load with the actual model remain unmeasured. See HANDOFF.md.
- Full verification: core-api 293, reasoning 987, voice-agent 335, scheduler 7, Vitest 146; TypeScript, production build, Ruff, and `eval/run_eval.py` all pass. Focused tests cover thresholds, silence gating, answered/unanswered escalation, label-only API transport and no audio file writes. Model-backed inference and physical-device performance remain unverified because the model asset is absent.
