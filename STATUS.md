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
  outdated replies are not spoken unless they ask a yes/no; direct file log `logs/voice-agent.app.log` plus
  session errors, because the console pipe delivered no session lines. UNVERIFIED live until the retest.
- Wrong reminder id 2 (07:00) deleted from the dev database.
- Tests run on Windows, Python 3.12: core-api 40, reasoning 196, voice-agent 17, scheduler 3 passed; ruff
  clean; web `tsc --noEmit` clean; eval 42/42, 12/12, 5/5 (regression only, synthetic). Real-speech
  regression (`eval/private`, git-ignored) 9 cases pass; turns 5, 6-8 and 12 await the speaker's ground truth.

## Next (in order)
1. Retest in a fresh Console session (T4 again): watch for late or out-of-order replies.
1b. TTS: per-reply WebSocket connect costs ~1 s; SSE through a pooled session looks faster. Needs an OK (see report).
2. T6 elder app via LiveKit + Gnani (remove browser speech) + core-api `/livekit/token`.
3. T8 spoken delivery of reminders/medicines. 4. ~~T9 Evon decision~~ DECIDED 2026-10-24: no Evon for the demo (rules-only; EVON_BASE_URL stays empty). OPENER_USER_IDS / BRIEFING_USER_IDS stay empty until T8 makes openers/briefings actually spoken.
5. T12 native-speaker review of distress + emergency lexicons. 6. T14 production proxy + auth.
