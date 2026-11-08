# HANDOFF (2026-11-04, memory + smarter companion on top of LLM-first understanding)

## Logical companion replies (2026-11-08)
- Generic normal-conversation no-hearing replies were removed. Empty/noise first turns are silent; after two consecutive empty/noise turns Arjun asks warmly for the elder to move closer. Topic uncertainty produces a specific clarification, with same-topic repeats suppressed. Markers are consumed as events before reasoning. Emergency/distress checks remain ahead of ordinary LLM handling.
- The reasoning path retries understanding once within the per-turn budget, shortens context to the last six exchanges, wraps raw speech as a possibly noisy transcript, and logs timeout/retry/sanitizer fallback causes without logging exception payloads. The voice endpoint waits up to 1.5 seconds for short/conjunction fragments; companion endpoint minimum remains 1.6 seconds. A TTS failure is logged and does not make Arjun speak a generic unrelated line.
- Baseline log measurement (Nov 6–8): 128 turns, one fixed fallback (0.8%), 69 LLM replies. One recorded fallback took 5006 ms, consistent with a timeout but not conclusive. The log does not retain enough cause detail to count sanitizer/JSON/rate-limit/STT/cutoff causes. Eleven event markers appear; five video-stop markers were incorrectly sent to the LLM in that historical sample.
- `eval/logic_eval.jsonl` has 80 synthetic multilingual/noisy/memory/cutoff cases. Live Sarvam strict-JSON judging of 50 recent LLM replies was not run because `SARVAM_API_KEY`, `ARJUN_LOGIC_EVAL_USER_ID`, and `REASONING_URL` are not configured; no historical conversation was uploaded for judging. Run `scripts/eval_logic.py` only with a synthetic test user and those environment variables.
- Full verification: core-api 298, reasoning 994, voice-agent 352, scheduler 7, Vitest 146, TypeScript/build, Ruff and `eval/run_eval.py` all pass. The web build emits the existing chunk-size warning; pytest cache writes are denied, so tests used workspace-local basetemp. Physical phone behavior and provider-level logicality remain unverified.

## Daily Telegram voice briefing (2026-11-07)
- Core-api composes 3-5 short Marathi sentences from the selected user's current-day medicine status, raw BP values,
  meal check-ins, and (only with `consent_distress_alert`) the existing mood word and paraphrased conversation highlight.
  It does not save or log briefing text. Sugar readings are not modeled in this repo yet, so no sugar values are invented.
- The family dashboard's **आत्ता सारांश पाठवा** button forces a send. The scheduler calls core-api every tick; core-api sends
  after household-local `BRIEFING_TIME` (default 20:30) for users with `daily_checkins` enabled. SQL dedupe is one attempt
  per user/day; a manual force can resend. Feed records `briefing_sent` or `briefing_failed` only after the outcome.
- `voice-agent` hosts an authenticated loopback Timbre endpoint on port 8002. It uses the agent's verified SSE mode,
  combines PCM frames to WAV in memory, then encodes Telegram-ready OGG/Opus with ffmpeg (available on this machine).
  Core-api sends it with caption "आजचा सारांश" using Telegram `sendVoice`. The pinned 1.8.6 plugin supports SSE;
  its model literal lists v2.0/v2.5. A key-backed one-word probe selected the same fallback as Arjun, `timbre-v2.5` / Omkar;
  configured v3.0 did not pass its probe and is not the plugin's declared model. No unverified warm tag is used.
- No Telegram command poller exists, so `/summary` was not added. No `.env` values or DB files were changed.
- Verification: core-api 287, reasoning 982, voice-agent 325, scheduler 7, web 145; TypeScript/build, Ruff and eval pass.
  A synthetic WAV converted to a valid OGG container locally. The real OGG endpoint request could not reach
  `api.vachana.ai` from this sandbox (outbound access denied); Telegram was not contacted. Phone test: start/restart with
  `scripts\\dev-up.ps1`, open the protected family dashboard,
  tap **आत्ता सारांश पाठवा**, then confirm Telegram receives one voice note with the stated caption. With `daily_checkins` on,
  confirm the scheduled send after the configured time; press the button again to verify explicit force-send. Check that a
  failed/unconfigured Telegram route yields a `briefing_failed` feed event, never a success claim.

## Daily health check-ins for the demo user (2026-11-07)
The demo user was silent because `daily_checkins=0` and no profile times were seeded; the engine and scheduler were
running. `scripts/seed_heerabai.py --apply` now sets user 1 to check-ins ON with opener 07:30-21:00, wake 06:30,
breakfast 08:30, lunch 13:00, snack 17:00, dinner 20:00, walk 18:00, BP 09:00, fasting sugar 08:00, after-lunch
sugar 15:00, address "आजी", and four medicine rows (बीपीची गोळी 09:00/21:00, शुगरची गोळी 08:30/20:30). It matches
medicines by `(name, time)` and switches off medicines outside the plan, so re-running is safe. The stored user name
cannot be changed through `PATCH /users/{id}`; only `address_as` is set.

Engine changes: quiet hours are 22:00-06:30; `ARJUN_CHECKIN_MAX_PER_DAY=14` applies to conversation prompts while
meals/snack/walk/BP/sugar are exempt; `ARJUN_CHECKIN_MIN_GAP_MIN=30`; every decision logs once as
`checkin <kind> asked|postponed:<reason>|missed`; the scheduler falls back to `GET /internal/checkin-users` when
`OPENER_USER_IDS` / `BRIEFING_USER_IDS` are empty. `walk_time`, `bp_check_time`, `sugar_check_time` and
`sugar_after_time` are optional and absent from the plan when unset. The dashboard can edit all of them and shows a
clear ON/OFF check-in toggle.

Phone test after `seed_heerabai.py --apply` and a restart: open the elder page and keep it idle. Expect a spoken
check-in inside the 07:30-21:00 window at the next due time (e.g. sugar 08:00, breakfast 08:30+30, BP 09:00), one
question at a time, at least 30 minutes apart, and a plain answer recorded on the family "आजचा दिवस" card. Confirm
nothing is asked 22:00-06:30 and that a busy/media/safety moment postpones it rather than interrupting. This is
automated-path coverage; no live phone or Gnani run was performed.

Runtime follow-up: the current core-api profile is ON and seeded as above. `logs/scheduler.log` proves a check-in was
queued, and the live delivery list shows it still queued; recent voice logs do not show that delivery being spoken,
so they cannot establish that a live elder session was open at its due time. During a family call the delivery loop
used to bypass queue lookup, leaving a check-in without its busy/postpone decision. The voice agent now sends a
separate call-active flag to reasoning: check-ins enter the normal 10-minute postponement policy and other deliveries
are not claimed for speech until the call ends. Automated regression tests cover both paths; a live phone run is still
required. `checkin_demo.py --plan-only` was not run because its check-in/card GET endpoints commit generated rows;
the no-database-write rule takes precedence. Its stale 45-minute/22:00-07:00 descriptions are corrected to 30 minutes
and 22:00-06:30.


## YouTube playback listening recovery (2026-11-07)
Diagnosis from the newest media session in `logs/voice-agent.app.log`: the open-media action was followed by turns
logged `ignored_media:true`; voice-agent wrote `ignored_media (54 characters; the words are not kept)`. At session end,
the log recorded `stream closed ... SOURCE_MICROPHONE`, `input stream detached`, then
`session closed {"reason":"participant_disconnected"}`. The transcript stream was still producing utterances before
the gate discarded them. The YouTube video path already embeds in `MediaScreen`; the inspected source did not have
visibility, pageshow, or focus recovery. This supports a stuck media-gate cause and an additional room/microphone
disconnect; it does not prove that a new tab caused the disconnect.

Fix: voice-agent media mode turns on only after the elder page reports actual player state `playing`. The web page
publishes `arjun.media` plus a changing `arjun.media.heartbeat` every 10 seconds; stop, ended, player error, page
hidden, unmount, voice stop, and 30 seconds without heartbeat turn it off and log transitions once. Stopping calls
reasoning `/media/stopped`, clearing pending media ask/choice and adding the single `[media stopped]` memory note.
YouTube remains embedded. The voice hook recovers on visibility/pageshow/focus, reconnects a lost room with bounded
backoff, republishes a missing/muted/ended microphone, restarts LiveKit audio playback, and republishes media state
to a fresh room. Browser capture keeps echo cancellation, noise suppression, and auto gain control enabled.

During playback, the local safety check still wins, short media controls pass without the wake word, the video
volume ducks to 20% while VAD reports speech and returns afterward, and media utterances are force-committed at
8 seconds. An STT error requests a fresh LiveKit session so the Gnani STT instance/stream is created again; the
page then reconnects to a fresh room. This is automated-path coverage, not a live Gnani or phone verification.

Verification: voice-agent 318, reasoning 969, core-api 269, scheduler 8, web 139; TypeScript, production build,
Ruff and `eval/run_eval.py` passed. Phone check remains required: play an embedded YouTube video; speak a bare
`बंद कर ना`; confirm it stops; say `आज काय आहे`; then test `पुढचं`, `मागचं`, volume, safety during playback, tab-hide
and return, and wait over 30 seconds after stopping to confirm ordinary turns continue.

## Gnani speech status update (2026-11-07)
The pinned `livekit-plugins-gnani==1.8.6` API does not expose an explicit Prisma model selector or the v3
Auto-LID, keyterms, speaker names, previous-context, `codemix`, and `transliterate` controls. The configured
STT therefore must not be called an explicitly selected Prisma v3.0 integration. It currently uses the
plugin-selected model with `mr-IN`, 16 kHz streaming, `transcribe`, and native numerals. Use
`python scripts/check_gnani.py` for a no-network key presence/whitespace and configuration check; it cannot
verify authentication. Do not print the previous `check_gnani.py` live response body. To proceed with v3,
obtain official protocol/API documentation or a Gnani-supported SDK that exposes the model and fields, then
implement and mock-test its documented wire contract before a live key check. Do not change LiveKit versions
without compatibility testing. Timbre remains configured to v3.0/Avinash with a v2.5/Omkar fallback; only
the v2.5 response has historical live evidence, and the complete voice turn remains unverified.

### Documentation follow-up (2026-11-07)
The official Gnani Prisma v3 product page and `gnani-vachana` repository now document `prisma-v3.0`,
`indic-auto`, language candidates, all four modes, keywords, topic, speaker names, previous text, and
detected-language results. This updates the prior statement that official protocol documentation was missing.
The pinned LiveKit plugin remains unchanged; its constructor still cannot select the model or expose those
controls. The published SDK examples confirm streaming model/language candidates/keywords, but do not show
the streaming wire format for every context option. No account-level entitlement or API authentication has
been checked, and no feature is marked live verified based on marketing/docs alone. See
`docs/ENGINEERING.md` for the current boundary and the Gnani sources linked from README.

## Where we are
Understanding is now LLM-first: one Sarvam call per non-safety turn gets the full sentence, the last turns and a
USER CONTEXT block, and returns strict JSON `{intent, slots, reply, confidence}`. The rule parser is a fallback
(timeout, provider error, invalid JSON, unknown intent, or confidence < 0.4 for an action) and every fallback is
logged with its reason. The safety floor (emergency/distress rules + the second look) still runs first and works with
the LLM and core-api down. Everything is committed locally, nothing is pushed.

## Latest owner decisions and implementation (2026-11-04)
- Boundary 10 is widened: general knowledge, festivals, meanings, everyday how-to and recipe basics may come from
  model knowledge. Recipe replies use 2-3 short steps and end with "व्हिडिओ लावू?". Health/medicine advice, doses,
  diagnoses and model-sourced news facts remain forbidden; news facts require an approved source.
- Facts are stored for Arjun's own use regardless of consent. Family fact lists require "share how she is doing";
  body-complaint facts require consent; deletion does not. See `CLAUDE.md` boundary 11.
- Profiles now carry editable `address_as`. Defaults are first name + "बाई", or "आजी" at known age 60+; the
  companion context tells the model to use this exact form and never invent "ताई". Existing SQLite rows are
  backfilled safely by `ensure_columns`.
- The sanitizer allows agreement with her own stated plan to rest; unprompted rest advice remains blocked. Initial
  "का" and "अहो" fillers are stripped.
- The first greeting after a day change gets the deterministic latest yesterday event fact, or yesterday's summary
  topic if no event exists. The LLM phrases that selected item. Idle family summaries use the configured LLM's strict 2-3-line,
  no-quotes/no-transcripts output; the rules summary remains the failure fallback.
- `graphify-out/` is ignored. `graphify-output/*.md` was scanned for keys, bot tokens and +91 phone numbers (zero
  matches) and is committed separately as architecture analysis.
- Verification: core-api 269, reasoning 950, voice-agent 310, scheduler 8; web 133, TypeScript, build, Ruff and
  intent/slot/distress/emergency evals pass. Dialogue run `final1` completed with d12=12/12, but sustained Gemini
  throttling prevented final2/final3 from completing (some cases were unjudged); rerun the three dialogue sweeps
  after provider recovery. No local commits were made because this requested evaluation remains incomplete.

## What changed (details in STATUS.md, design in docs/ENGINEERING.md §14)
- `services/reasoning/reasoning_svc/evon.py`: `understand_turn()` (unified prompt, strict JSON, legacy intent names
  still accepted and marked `legacy`, plain prose treated as a chat reply), companion prompt, narrowed sanitizer,
  `max_tokens` default 250, temperature 0.5.
- `services/reasoning/reasoning_svc/turn.py`: LLM-first `handle`; `_understand`, `_user_context`, `_parsed_from_llm`,
  `_chat_reply`; pending/draft/media-choice/check-in/BP state resolved from LLM slots; deterministic state answers
  (yes/no, stop, medicine taken, time/next-up, greeting, hearing check) stay rule-decided; media behaviour preserved.
- `services/reasoning/reasoning_svc/config.py`: 250-token default, temperature 0.5, context limits.
- `services/reasoning/reasoning_svc/parser.py`: a sentence that only mentions "औषध" is no longer a medicine turn.
- `services/reasoning/reasoning_svc/core_client.py`: `checkin_card()` (`GET /users/{id}/checkins/card`) and
  `wellbeing_today()` (`GET /users/{id}/wellbeing/today`) for the context block.
- `services/reasoning/reasoning_svc/main.py`: `TurnOut.action: dict[str, Any]`.
- Tests: `test_llm_policy.py` rewritten to the new contract; `test_llm_config.py`, `test_reply_quality.py`,
  `test_llm_compare.py`, `test_app_commands.py`, `test_media_intents.py` aligned.
- Eval: `eval/companion_eval.jsonl` (50 realistic Marathi utterances), `scripts/eval_companion.py`
  (`--eval` / `--replay N`, `--legacy` for the before measurement, `--tag` names the saved rows).

## Verified (2026-11-04)
- reasoning 894, core-api 244, voice-agent 209, scheduler 8, vitest 114; `tsc --noEmit` and `ruff check .` clean.
- `eval/run_eval.py`: intent 42/42, slots 12/12, distress 5/5, emergency 87/87, false alarms 0/12.
- `scripts/eval_companion.py --eval` (fresh throwaway user per utterance) before vs after:
  46/50 vs 50/50 turns reached a reply (4 requests failed in the old stack, 1 judge failure); relevant 1.47 -> 1.54,
  understood 1.58 -> 1.62, about_her 1.40 -> 1.38, solution 0.91 -> 0.98, natural_marathi 1.73 -> 1.8,
  safe 1.0 -> 0.98; action intent 20/27 -> 26/30; routes 17 LLM / 29 rules -> 49 LLM / 1 rule;
  banned "जमत नाही / आता कसं" lines 3 -> 0. The before run is the previous commit in a worktree with `--legacy`
  (its 80-token configuration).
- `--replay 30` before vs after: 23/30 LLM + 7/30 rules -> 28/30 LLM + 1 rule (1 client timeout, 29 answered);
  0 `finish_reason=length`; 1 sanitizer rejection (medical) after.
- The eval starts the stack in a temp directory with a throwaway SQLite file and forces Sarvam for both the turn and
  the judge, so no repo file, log, database or secret was touched. Each utterance now gets its own user: the dataset
  is 50 independent sentences, and a shared user leaked a pending reminder and an undo window into the next item.

## Known weak spots (real, not hidden)
- Two action questions still get the fixed doctor line instead of a useful answer: "औषधांची गोळी किती घ्यायची?" and
  "माझी गोळी चुकली तर काय करू?" (dose guidance is deliberately forbidden - route them to the family/doctor, do not
  invent a dose).
- Recipe how-to requests now stay in companion chat and are answered with short basics; explicit video requests
  remain media actions. This is covered by a regression test.
- Severe STT noise ("मोचात घालून", long garbled strings) honestly answers "समजलं नाही" and offers the family. That is
  the intended floor, not a bug, but it is still the loudest pattern in the replay.
- One replay turn hit the script's 30 s client timeout; the reasoning call itself is bounded, but a slow Sarvam turn
  plus the safety second look can exceed the eval client. Not seen from the voice path.
- The judge averages barely move (relevant +0.07, solution +0.07, about_her -0.02, within run-to-run noise at
  temperature 0.5). The measured wins are the turns that completed (46 -> 50), the action intents (20/27 -> 26/30),
  the rule share (29/50 -> 1/50) and the zero banned lines. Quote those, not a "quality score went up".

## Do this first
1. **Root `.env` still has `LLM_MAX_TOKENS=80`.** The code default is 250 but the live stack reads the env line, so
   replies stay short/cut until it is changed (or removed). It was deliberately not edited here. The eval child sets
   the value itself, so the before/after numbers above are unaffected.
2. If you change the companion prompt, re-run `scripts/eval_companion.py --eval --tag <name>` and compare against the
   after numbers above; do not judge by reading one reply.

## Phone test (about 10 minutes)
1. Put `ARJUN_ACCESS_CODE=<6+ chars>` in the root `.env` (never printed; see `.env.example`), then `scripts\dev-up.ps1 -Phone`.
   It prints the full links WITH the code (`<tunnel>/?user=1&k=<code>` and `<tunnel>/?view=family&user=1&k=<code>`). Open the
   elder link on the phone, tap to start, let the greeting finish.
2. Talk normally for a minute: a story with "औषध" in it must stay a story; "आज काय करायचंय?" must mention her real
   day; "मला एकटं वाटतंय" must point at a named family member, not a generic line.
3. Ask a reminder ("उद्या सकाळी दहाला ... आठवण करून दे"), confirm it is read back with the right day/time, then ask
   "उद्या काय आहे?" and check the same reminder comes back from SQL.
4. Turn the network off for a moment / stop reasoning and say "मला छातीत दुखतंय": the emergency flow must still run.

## After demo (from graphify-output/ISSUES.md; deliberately NOT done before Nov 8)
- **Per-user authorization (issue 2).** There is still ONE shared API key and `user_id` is a path parameter nobody checks
  against the caller. The tunnel lock (2026-11-04) now limits a phone to its role's routes, but an elder link for user 1
  can still read user 2. Real fix: per-user tokens, a service secret on `reasoning` (it has no auth, only a loopback
  bind), no key in the browser path. Frozen item "login/roles".
- **Split `TurnEngine` (issue 4).** `reasoning_svc/turn.py` is ~2,200 lines, ~145 methods and per-user state in
  in-memory dicts. Seams, least risky first: media cards, delivery rendering, check-in answers, companion chat. Extract
  the safety path (the top of `handle`) last, and keep every suite green after each move. Same story, smaller:
  `Dashboard.tsx` (1,155 lines) and `core_api/main.py` (767 lines).
- **One browser media pipeline (issue 5).** `voice/state.ts::parseActionAttribute` -> `elder/media.ts::planAction/embedSrc`
  (used by `useAppActions`) and `voice/action.ts::parseAction/embedSrc` (used by `MediaScreen`, `Gallery`) do the same job
  twice and can drift. Merge into one parser and one `embedSrc`.

## Memory task progress
- core-api user_facts store + family dashboard list + tunnel-lock routes: done (commit 1 of 3)
- reasoning session memory + life facts + remember/forget + smarter prompt: done (commit 2 of 3)
- reasoning memory (session + life facts) + eval + docs: done (commit 3 of 3)
- What is new, in four lines: every spoken line is in one session history; silence compresses it (never deletes);
  facts about her life live in core-api `user_facts` and go into every LLM call; "हे लक्षात ठेव / हे विसरून जा" works.
- **Do this first:** remove `LLM_MAX_TOKENS=80` from the root `.env` (replies get cut) and note `LLM_HISTORY_EXCHANGES`
  no longer controls the memory (use `ARJUN_SESSION_EXCHANGES`).
- **Decide:** the prompt answers festival / meaning / how-to questions from model knowledge, which is wider than
  boundary 10 as written (see STATUS.md); recipes and health are still refused.

## Elder started video calls (2026-11-07)
- Voice intent `VIDEO_CALL` is deterministic for explicit Marathi/English video-call wording and also offered to the LLM-first intent schema. A named contact wins; otherwise the son, then first non-doctor family contact. Existing “मुलाला फोन लाव” still uses the voice-only reminder intent. Safety is checked first.
- Core API creates `video_calls` rows, sends one Telegram ring message with a signed 30-minute join URL, dedupes the same ringing contact for two minutes, changes to answered on family join, and marks missed after 60 seconds with a return button and `video_call_missed` feed notification. Camera publishing is enabled in the elder LiveKit token, but the camera activates only after a video-call action.
- The elder calling screen shows local preview and a ringing tone, then family video plus self preview; end, page hidden, safety, missed, or error paths release media tracks. Family join view publishes mic/camera and offers mute, camera, and hang-up controls. Arjun suppresses ordinary turns while family is present; safety phrases still reach reasoning.
- Verified: core-api 273, reasoning 973, voice-agent 320, scheduler 8; Vitest 144, TypeScript, production build, Ruff, and dialogue eval 42/42 intent, 12/12 slots, 5/5 distress, 87/87 emergency with 0/12 false positives. Browser/device camera behavior and Telegram delivery still need the phone test below.

### Named-contact call recognition
Logs show exact STT transcripts `ठीक आहे राहुलला कॉल करणारे` (CHAT) and `राहुलला कॉल कर` (CHAT, no action). The latter
was parsed too late, after “कर” could be treated as a short affirmative, and LLM-first understanding was allowed to
replace call parsing with `CHAT`. Direct named-contact call commands now emit the existing LiveKit video-call action;
the rule takes precedence over LLM chat. “Tell Rahul to call me” remains a caregiver request, while a non-imperative
mention remains chat. Regression tests cover the exact command and the three Marathi / Romanized variants.

### Video-call phone test
1. Start the local phone stack with `scripts\dev-up.ps1 -Phone`; open the elder link and allow microphone/camera access.
2. Say “व्हिडिओ कॉल कर”. Confirm Arjun says “{name}ला व्हिडिओ कॉल लावतो, थांबा.” and shows the preview/ringing screen. Check the family Telegram receives “📹 {elder} व्हिडिओ कॉल करत आहेत” with “उचला”.
3. Tap “उचला” on a second phone. Confirm the family sees the elder and self preview, while the elder sees family video and a small self preview. Say “बंद कर”; confirm both sides disconnect and the elder page listens to a fresh normal question without reload.
4. Repeat without answering. After 60 seconds confirm the elder gets the missed-call reply and Telegram gets the “परत करा” button. Also test the red end button, page hidden/return, and “छातीत दुखतंय” during a call.

### Video-call drop / STT recovery regression (2026-11-07)
- Calls 3/4 showed `[video_call_stopped]` before family joined because the elder screen ended on transient poll failure or page hide. STT idle closure also invoked `ctx.shutdown`, replacing the room and invalidating the join link.
- The elder screen now tolerates transient poll failures and hidden-tab recovery; UI markers are filtered from transcript history and intercepted before reasoning; the agent stays silent during ringing/active calls apart from safety. Family disconnect gets a 15-second grace period. STT errors keep the job alive so the pinned LiveKit 1.8.6 pipeline can recreate its stream in place.
- Verification after connection fix: core-api 274, reasoning 973, voice-agent 321, scheduler 8; Vitest 144, TypeScript, production build, Ruff, and dialogue eval pass. Tests used a workspace-local pytest temp root because this environment cannot scan the user's system temp directory.
- The latest connection trace also exposed that `[video_call_stopped]` uses the LiveKit `lk.chat` callback; that event path is now intercepted before reasoning too. `/family/join` now only issues the LiveKit token; `/family/calls/answer` changes the call to answered after the family client connects and publishes camera, and terminal family room disconnects trigger retries in the same room before the call is ended.
- Test on a phone: start a video call, leave it ringing for at least 30 seconds while Arjun speaks/re-renders, then join from the family Telegram button at about 13 seconds on another run. Confirm both streams stay connected. Toggle the elder tab away and back; say “बंद कर” and then a normal question. Leave a separate call unanswered for 60 seconds and confirm the fixed missed-call line. Keep the session quiet for 60 seconds to check STT remains in the same room/job and then speak again.

### Hearing-friendly speech (2026-11-07)
- Speech style is stored on the user profile as `{rate, volume, simple}`. The family dashboard can set all three values; voice commands set slow/loud, “नेहमीसारखं बोल” resets defaults, and two repeat requests within ten minutes turn on slow + simple wording.
- “काय?”, “पुन्हा सांग”, “परत सांग”, and “समजलं नाही” replay Arjun’s in-memory last reply. The simplifier only receives Arjun’s prior line, is instructed to keep identical meaning and numeric/time tokens, and its output is rejected if those tokens change. Failure falls back to the original line.
- No Timbre speed/volume API parameters were verified for the pinned 1.8.6 plugin and current key, so the voice agent does not send speculative parameters. Slow speech adds pause punctuation; loud speech boosts the elder page Arjun player to full gain and restores the saved local level when normal is selected.
- Verification: core-api 287, reasoning 985, voice-agent 326, scheduler 7; Vitest 146, TypeScript/build, Ruff, and eval 50/50 intents passed. Pytest used separate workspace-local temp roots because the default Windows temp directory is access denied.
- Phone test: open the elder page and ask a question containing a time. Say “पुन्हा सांग” and confirm the same time is repeated with simpler wording. Repeat once more within ten minutes and confirm slower, simpler replies. Say “मोठ्याने बोल”, then “नेहमीसारखं बोल”. On the family dashboard, change pace, volume, and simple wording and start a fresh voice turn to confirm the profile takes effect.
## Voice metrics and judge evaluation (2026-11-07)
- Turn logs now expose aggregate numeric timings at authenticated `GET /metrics/voice?hours=24`: STT EOS→final, final→reasoning, reasoning→first audio, EOS→speaking, and barge-in start→agent stopped. Core-api reads the shared turnlog path; Docker mounts `eval/results` read-only. Dashboard displays numeric p50/p90 bars only.
- Added `scripts/voice_report.py` and numeric-only committed `eval/REPORT.md`; report covers synthetic intent/slot, emergency recall/false alarms, BP parsing, code-mixed sample size, judged dialogue dimensions, and local latency. Sugar-number parsing is not implemented and is labeled unscored. No transcripts or Prisma WER are included.
- Barge-in instrumentation records a separate transcript-free metric event. VAD interruption threshold is configured to 100 ms and false interruptions resume after 2 s. Synthetic test confirms a 250 ms stop measurement is represented; existing local history has 0 live barge-in samples, so the <=300 ms on-device target remains unverified and must be measured on a phone.
- Latest local aggregate (128 turns, 81 complete): STT p50/p90 673/784 ms; final→reasoning 160/980 ms; reasoning→first audio 656/869 ms; EOS→speaking 4516/6280 ms; barge-in n=0. Tests: core-api 290, reasoning 985, voice-agent 328, scheduler 7, web 146; TypeScript, build, Ruff, and eval pass.
- Phone check: open family dashboard and confirm the Voice performance card shows numeric p50/p90 values. On the elder phone, start Arjun speaking, interrupt with a short phrase, and verify audio stops within 300 ms. Repeat several times; the family card/report should gain barge-in samples and show their p50/p90. No transcript should appear on the family dashboard.

## Optional non-speech sound events (2026-11-07)
- Added `ARJUN_SOUND_EVENTS=0` default and a Windows CPU ONNX Runtime adapter for a supplied YAMNet ONNX file plus its class-map CSV. It reads the LiveKit mic stream through a transparent audio tee and classifies transient 0.96-second windows on one bounded worker thread with an average 10% CPU-time budget. The queue is bounded; congestion drops classifier frames rather than delaying speech recognition.
- Event mapping keeps only `cough`, `scream`, `crying`, or `bang` plus confidence. Core-api stores those scalar labels/scores and serves a daily cough-event trend. It never accepts audio; no waveform or extracted features are written to disk or logs. Cough detections are episode counts with a 60-second per-label cooldown, not a medical cough count.
- A scream/shout or bang must be followed by a low-energy window before Arjun asks `तुम्ही ठीक आहात का?`. If the elder does not begin speaking within 20 seconds, the sound-event route calls the same core-api emergency flow as other physical emergencies. Crying gets one gentle fixed check-in; no diagnosis is made.
- Environment check: the workspace has CPU `onnxruntime` 1.31.0, but no YAMNet ONNX model or class map. The production classifier was not run and stays inactive; if `ARJUN_SOUND_EVENTS=1` with no valid model path, voice service logs the model-unavailable reason and continues. A third-party ONNX conversion is described at https://huggingface.co/audiomagic/yamnet-onnx as an Apache-2.0 conversion of Google's YAMNet; model file/phone performance was not verified here. Supply a model and adjacent `yamnet_class_map.csv`, set `ARJUN_SOUND_EVENTS=1` and `ARJUN_SOUND_MODEL_PATH` locally.
- Automated coverage: sound thresholds, scream/bang then silence, 20-second no-answer escalation/cancel-on-answer, transient audio/no file writes, label-only transport, persistence and daily cough aggregation. Synthetic waveforms and mocked inference do not prove event recall or false-alarm rates on a phone.
- Phone test after supplying a valid model: set the two variables locally and restart `scripts\dev-up.ps1`; confirm the dashboard says detection is on. Play synthetic cough/shout/glass clips near the elder mic and verify only cough counts trend, scream/bang followed by silence asks the fixed check-in, an answer cancels the 20-second timer, and silence raises the existing emergency banner. Repeat with the flag off and confirm no event rows/check-ins occur. Do not use real calls or recordings for the demo.
# Accounts and per-user authorization — Phase 1 (2026-11-07)

Implemented opt-in core-api authorization with `ARJUN_AUTH=0` by default. Account passwords use Argon2id; sessions
are opaque, HttpOnly cookies with 12-hour sliding expiry and a 30-day cap. Family membership scopes each user route,
one-time invites add a family member, and a 15-minute pairing code binds an opaque elder-device cookie to one user.
Device/invite/pairing values are stored as hashes. Login and pairing attempts are rate-limited. The existing
service-to-service API key remains valid, and auth-off test/development behavior stays compatible. Docker Compose
passes through `ARJUN_AUTH` without changing any `.env` values.

Tests added for account signup/session/logout, normalized email, membership isolation, elder device binding, login
throttling, raw-story route denial, and auth-off compatibility. Full suites pass: core-api 297, reasoning 987,
voice-agent 335, scheduler 7, web 146, plus TypeScript/build, Ruff and eval. Pytest used workspace-local `--basetemp`
because the system temp directory denies access. Do not treat the account flow as ready for the existing web tunnel: its
proxy injects the service key, and browser login/account management are Phase 2. Keep `ARJUN_AUTH=0` until Phase 2
provides the authenticated browser integration. Phase 3 shared reasoning/call state and multi-worker safety remain
unimplemented. No database files were touched; `create_all` creates new tables on service startup.

Phone/API smoke steps after Phase 2 integration: enable `ARJUN_AUTH=1` in the local process environment, restart
core-api, create a synthetic family account, add a synthetic elder, issue a pairing code, redeem it on the elder
device, and confirm that device can fetch only its paired elder's day. Sign in as a second family account and confirm
requests for the first account's elder return 403. Invite the second account to verify a single-use family membership.
