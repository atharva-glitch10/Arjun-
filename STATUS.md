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
- No `YOUTUBE_API_KEY` is configured on this machine, so the real first-match search was NOT run: the scripted run showed the no-key fallback (YouTube results
  page). Mocked-API tests cover the key path.
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
