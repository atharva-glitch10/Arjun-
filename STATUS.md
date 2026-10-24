# STATUS (2026-10-24)

## Done
- T1 first commit; T2 keys rotated and verified (LiveKit registered 14:06 / 14:18; Gnani TTS 200 with
  timbre-v2.5 + Omkar); T3 dotenv allowlist + `scripts/dev-up.ps1`.
- 2026-10-24 review fixes (see "Changes" below).

## Changes on 2026-10-24
- **Agent dispatch**: worker now registers as `agent_name="arjun"`; `scripts/make_token.py` adds an
  explicit agent dispatch to the token's room config and uses a fresh room name per run
  (dispatch only happens when the room is created). Fixes "agent never joins" from 2026-10-21.
- **No silence on failure**: `bridge.reply_or_fallback` speaks a fixed line if reasoning errors,
  times out (5 s) or returns bad JSON; one shared HTTP client. TTS failure is logged and retried
  once with the fallback line.
- **Physical emergency path** (reasoning): chest pain / breathing / fall now / fainting / bleeding ->
  fixed 112 template, pending actions cleared, event recorded. Overrides distress. Past-tense story
  phrasing ("पडले होते") excluded. Lexicon UNVERIFIED.
- **core-api outage** no longer causes a 500 in reasoning: the fixed error template is returned.
- **Auth**: constant-time key comparison; core-api refuses to start with an empty `CORE_API_KEY`
  (tests set `ARJUN_TESTING=1`).
- **Honesty**: scheduler comments no longer claim LiveKit delivery; dashboard shows fired reminders
  as "Due · not spoken yet".
- **Pins**: livekit-agents / livekit-plugins-gnani / livekit-plugins-silero == 1.8.6.
- **Repo**: `arjun-ui/` -> `design/` (stale CLAUDE.md copy removed); `agents-playground/` removed
  from the repo and git-ignored; CLAUDE.md restored rules (medicines, readings, emergency, frozen
  list, contest, Ghar, voice-path facts).
- Tests run 2026-10-24 (Linux, Python 3.13): core-api 38, reasoning 130, voice-agent 9,
  scheduler 3 passed; ruff clean; web `tsc --noEmit` clean; eval 33/33, 7/7, 5/5 (regression only).
  NOT run: the live agent, LiveKit, Gnani (needs your machine and keys).

## After the T6 hand test (2026-10-24 evening)
- Found: the hand-test reminder was never saved. Prisma wrote the elder's "हो" as "हो हो हो" + "कर" x21; the 4-word
  confirmation rule missed it, the long text became a "keep your story?" offer that REPLACED the pending reminder.
- Fixed (tests first): A repetition collapse + all-yes answers at any length; B a pending question can only be
  answered, corrected or cancelled and expires after 5 min; C filler words out of the task; D dashboard refresh;
  E the agent serves the token's user id; F `scripts/clean_demo_db.py` (dry run by default). The F cleanup has NOT
  been applied: it waits for the speaker to approve the printed list. Emergency vs family-alert consent is still
  an undecided policy: nothing changed there.
- Tests: core-api 67, reasoning 319, voice-agent 45, scheduler 3, vitest 21 passed; ruff and `tsc` clean.

## Hosted LLM for open conversation (built 2026-10-24, NOT yet run against a real provider)
- Models, truthfully: **Gnani Prisma** (speech in) + **Gnani Timbre** (speech out) + a **hosted non-Gnani LLM** for
  open conversation, chosen by `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` / `LLM_PROVIDER_NAME` (`EVON_*` are
  aliases). **Evon is not used.** No key or provider is in `.env` yet, so reasoning runs rules-only and the
  canned companion lines are still what Arjun says.
- Used ONLY for companion/chat replies and for turns the rules return UNKNOWN; care commands, times, medicines,
  confirmations and safety never wait for it, and emergency/distress run before any call. For UNKNOWN turns it may
  only suggest a short list of intents, still behind the pending action + spoken yes. The elder's words in those
  turns go to the provider (synthetic data only for the demo).
- Limits: 4 s budget per turn for all calls, `max_tokens` 120, last four exchanges, fixed temperature, no name or
  contacts sent; one log line per call (provider, model, latency, tokens; no text). Replies are cut to two sentences
  and replaced by the fixed line if they claim to be human, say "I missed you", give medical advice, recite
  recipes/facts, or use the wrong script (a heuristic safety net, not a proof).
- `eval/llm_compare.py` (20 sentences + 10 companion prompts) is written and tested against a fake client; it has
  NOT been run on a real provider. Open question 5 (is a non-Gnani LLM allowed in the entry) is still open.
- Tests: reasoning 281, core-api 56 passed; ruff clean; eval 42/42, 12/12, 5/5.

## T6 built (2026-10-24): elder app through LiveKit + Gnani
- `POST /livekit/token` (core-api, same auth): 600 s token, fresh room per call, explicit "arjun" dispatch,
  mic-only publish, secret server-side. The Vite proxy injects the API key; the browser never reaches reasoning.
- Reasoning returns `screen` (reply | story | confirm | saved | safety); the agent publishes `arjun.screen`,
  `arjun.turn`, `arjun.reply` as participant attributes (state, not events). One `Responder` path serves spoken
  and tapped turns (taps arrive as text on `lk.chat`). Turn log now splits endpointing / reasoning / TTS.
- Web: `useArjunVoice` + pure `shownFor` (safety wins over every state; plain failure screen with a big retry).
  All browser speech removed (`scripts/check_no_browser_speech.py`, also a test). Replay button dropped.
  Medicine prompts are screen-only and labelled so until T8.
- Verified WITHOUT a browser (LiveKit Python client): token via the proxy 200, agent dispatched, tapped text gave
  confirm -> saved -> safety and story / reply screens with the agent speaking. NOT verified in a real browser:
  mic permission, audio playback, live transcription text, the screens themselves. First tap to agent listening:
  3.5 s (first tap after a worker restart; 7.3 s on an earlier run) and 1.8 s on the next (script timings, not the browser).
- Tests: core-api 54, reasoning 221, voice-agent 32, scheduler 3, vitest 13 passed; ruff and `tsc` clean; eval 42/42, 12/12, 5/5.

## After the first real-speech test (2026-10-24, 14 turns, see eval/results/RESULTS.md)
- **Latency**: `localhost` cost ~2 s per hop on this Windows machine; all service URLs now use `127.0.0.1`.
  One `/turn` round trip: median 2334 ms before, 351 ms after (5 runs each).
- **Never guess**: a clock word with no readable hour no longer falls back to the wake time; Arjun asks
  "किती वाजता?". The 10:00 doctor reminder that was saved as 07:00 is reproduced by a test and fixed.
- **Hour words** (Marathi/Hindi, incl. साडे/सव्वा/पावणे/दीड/अडीच) are converted to digits; readback wording
  changed to "{when} आठवण ठेवू का: {task}?".
- **New rules**: greeting, hearing check, long "no" with a pending reminder cancels it and asks again,
  "उद्या काय आहे" lists tomorrow (core-api `GET /users/{id}/day?on=YYYY-MM-DD`, read-only).
- **Voice agent**: turn log keyed by transcript (the old one paired replies with the wrong sentence);
  outdated plain replies are not spoken (safety replies and yes/no questions always are); direct file log `logs/voice-agent.app.log` plus
  session errors, because the console pipe delivered no session lines. UNVERIFIED live until the retest.
- Wrong reminder id 2 (07:00) deleted from the dev database.
- Tests run on Windows, Python 3.12: core-api 40, reasoning 207, voice-agent 20, scheduler 3 passed; ruff
  clean; web `tsc --noEmit` clean; eval 42/42, 12/12, 5/5 (regression only, synthetic). Real-speech
  regression (`eval/private`, git-ignored) 9 cases pass; turns 5, 6-8 and 12 await the speaker's ground truth.

## Next (in order)
1. Retest in a fresh Console session (T4 again): watch for late or out-of-order replies.
1b. TTS: per-reply WebSocket connect costs ~1 s; SSE through a pooled session looks faster. Needs an OK (see report).
2. T6 elder app via LiveKit + Gnani: BUILT 2026-10-24, awaiting the speaker's hand verification in a browser
   (token endpoint, agent attributes + tap path, web hook and screens, browser speech removed). See the T6 section.
3. T8 spoken delivery of reminders/medicines. 4. ~~T9 Evon decision~~ DECIDED 2026-10-24: Evon is not used. Open conversation will use a HOSTED NON-GNANI LLM (built, tested with mocks, NOT configured or run live yet: no key in .env, see `eval/llm_compare.py`). Gnani = Prisma + Timbre. OPENER_USER_IDS / BRIEFING_USER_IDS stay empty until T8 makes openers/briefings actually spoken.
5. T12 native-speaker review of distress + emergency lexicons. 6. T14 production proxy + auth.
