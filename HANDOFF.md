# HANDOFF (2026-11-04, memory + smarter companion on top of LLM-first understanding)

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
