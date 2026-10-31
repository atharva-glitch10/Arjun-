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
