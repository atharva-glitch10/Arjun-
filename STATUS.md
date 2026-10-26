# STATUS (2026-10-26)

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
  companion/chat replies and turns the rules cannot read; 4 s budget per turn, 120 tokens, last four exchanges,
  boundary-checked replies, per-call log without text. `eval/llm_compare.py` is tested on a fake provider.

## Verified vs NOT verified
- **Verified by the speaker in the browser (2026-10-24, self-reported):** the 10:00 confirm card showed. The logs
  match for the card (the 17:15:30 turn read back "उद्या सकाळी 10:00 वाजता आठवण ठेवू का: ...").
- **Reported by the speaker but NOT corroborated by the logs:** "a spoken हो saved the reminder". At 17:15:45 the
  recognizer returned junk and that reminder was rejected (fixed afterwards by A and B); the only saved doctor
  reminder (id 2) came from the 14:00 Console session, and `turns.jsonl` has no voice turn after 17:17 on 24 Oct.
  To be re-checked WITH log evidence in the T8 hand-test session.
- Verified by tests (core-api 76, reasoning 327, voice-agent 45, scheduler 3, vitest 24; ruff and `tsc` clean;
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
1. **T8** (spoken reminders and medicines, scheduler in dev-up, idle close, room pre-warm): plan written, waiting
   for the speaker's OK; then ONE hand-test session for the whole checklist.
2. **LLM**: add `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_PROVIDER_NAME` to a SEPARATE env file and run
   `python eval/llm_compare.py --env-file <that file>`; review the numbers before putting them in the live `.env`
   (the live path reads the same names and turns on at the next restart).
3. **T8 spoken delivery** of reminders and medicine prompts (scheduler -> the voice session), then turn on
   `OPENER_USER_IDS` / `BRIEFING_USER_IDS`.
4. Decisions waiting for you: TTS over SSE with a pooled connection (saves ~1 s per reply), pre-warming the room
   when the elder page opens, closing an idle voice session (credits), a "repeat last line" RPC.
5. Demo: main post ~Nov 1, submission by Nov 8 (deadline Nov 10). Native-speaker review of the safety lexicons (T12),
   production proxy + auth (T14), disclose the models truthfully in the posts.
