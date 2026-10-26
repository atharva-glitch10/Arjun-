# Arjun - measured results

Only numbers that were measured are listed here (CLAUDE.md boundary 13). No WER is reported
(Gnani EULA clause 16 is unresolved); transcripts are shown so a human can judge them.

## T4: first real-speech test (2026-10-24, after 13:06 IST)

**Setup.** LiveKit Console session, room `console-eca7dbd0`, worker `agent_name: "arjun"` dispatched.
Prisma STT `mr-IN`, streaming. Timbre TTS `timbre-v2.5` / voice `Omkar`. Evon OFF (rules only;
`evon_configured: false`). One speaker, quiet room (as reported by the speaker, not measured).
Synthetic user 1. BVC noise filter on. Credits used: **not yet provided** (read from the Gnani dashboard).

**Sample.** 14 final transcripts reached reasoning (14 `POST /turn` calls). 19 rows were written to
`turns.jsonl`; 5 rows are fragments (end-of-speech with no final transcript). n = 14 is a smoke test,
not an accuracy measurement.

**How the table was built.** The turn log pairs each reply with the wrong transcript for the first
9 rows (see "Findings", item 2), so intent and source were recovered by replaying the 14 transcripts
through the real `TurnEngine` (Evon off, in-memory core-api) in first-in-first-out order. All 14 live
replies were reproduced exactly, so the pairing is confirmed. Intent/source are therefore replayed,
not logged live. Source is `rules` for every turn (Evon is off).

Categories: (a) parser gap on a care command, fixable with rules; (b) open conversation that needs an
LLM; (c) STT error; (d) bug.

| # | Prisma final transcript | Intent | Source | Mode | Arjun's reply | Verdict |
|---|---|---|---|---|---|---|
| 1 | हॅलो | UNKNOWN | rules | care | मला नीट समजलं नाही. कृपया पुन्हा सांगा. | wrong: a greeting is "not understood" (a) |
| 2 | हॅलो | UNKNOWN | rules | care | मला नीट समजलं नाही. कृपया पुन्हा सांगा. | wrong (a) |
| 3 | हा आज काय | LIST_TODAY | rules | care | आज तुमच्यासाठी कोणतीही आठवण नाही. | right; "हा" extra, "आहे" missing (c, minor); spoken ~20 s late (d) |
| 4 | हां आता ऐकू येतंय का तुला | CHAT | rules | companion | अजून सांगा, मी ऐकतोय. | weak: does not answer "can you hear me" (a) |
| 5 | अरे मंद बोड्याच्या जरा मंद येस का तू | CHAT | rules | companion | मग पुढे काय झालं? | unknown, speaker didn't recall what was said (looks garbled, c unverified) |
| 6 | अरे लगा मी तुझ्याशीच बोलतोय तू बोलती माझ्याशी हा | CHAT | rules | companion | ते कोणासोबत होतं? | wrong: user talks to Arjun, reply is a canned story prompt (b) |
| 7 | पुन्हा सोबत म्हणजे काय तुझ्यासंगत बोलतोय | CHAT | rules | companion | हे तुम्ही तुमच्या माणसांना कधी सांगितलंय का? | wrong, off-topic (b) |
| 8 | माझ्या माणसांना का सांगू तुझ्यासोबत बोलतोय मी | CHAT | rules | companion | अजून सांगा, मी ऐकतोय. | wrong, off-topic (b) |
| 9 | आज काय आहे | LIST_TODAY | rules | care | आज तुमच्यासाठी कोणतीही आठवण नाही. | right |
| 10 | उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे आठवण कर मला | CREATE_REMINDER | rules | care | दहा डॉक्टरकडे जायचं साठी उद्या सकाळी 7:00 वाजता आठवण ठेवू का? हो किंवा नाही सांगा. | WRONG time (7:00, not 10:00) and garbled task (a)+(d) |
| 11 | सकाळी दहा वाजता डॉक्टरकडे जायचं आहे दहा डॉक्टरांकडे नाही जायचं | CHAT | rules | companion | मग पुढे काय झालं? | wrong: a correction while a confirmation was pending was treated as chat (a); tail may be STT (c, unverified) |
| 12 | उद्या आज काय आहे | LIST_TODAY | rules | care | आज तुमच्यासाठी कोणतीही आठवण नाही. | unknown, speaker didn't recall what was said |
| 13 | उद्या सकाळी दहा वाजता डॉक्टरांकडे जायचं आहे आठवण कर मला | CREATE_REMINDER | rules | care | दहा डॉक्टरांकडे जायचं साठी उद्या सकाळी 7:00 वाजता आठवण ठेवू का? हो किंवा नाही सांगा. | WRONG time and task (a)+(d) |
| 14 | हो हो ठेव हो | CONFIRM_YES | rules | care | ठीक आहे, आठवण नोंदवली. | parse right; it saved the wrong 07:00 reminder |

Tally of the 14 turns: clearly right 3 (#3, #9, #14 parse); wrong or weak 10; unverified 1 (#12).
Failure categories among the wrong or weak ones: (a) 6 (#1, #2, #4, #10, #11, #13), (b) 3 (#6, #7, #8),
(c) 1 probable (#5). Bugs (d) cut across turns and are listed below.

## Doctor reminder (reminder check)

The CREATE_REMINDER intent was recognised and a reminder was created, but with the **wrong time**.
`GET /users/1/reminders` returns:

    id 2  task: "दहा डॉक्टरांकडे जायचं"  due_at: 2026-10-25T07:00:00  status: pending

Expected: tomorrow 10:00, task "डॉक्टरकडे जायचं". Cause: the parser reads clock hours only as digits
(`_HOUR_MARK` is `(\d{1,2})\s*(?:vajta|वाजता|...)`), so the word "दहा" is not a time. With no clock
found, the bare period word "सकाळी" falls through to `elif period and not draft.time:` and silently
becomes `profile.wake_time` (07:00). "दहा" is not in `STOP`, so it stays in the task text. This
violates the "never guess" rule (CLAUDE.md boundary 3). The reminder is still in the database.

## Latency (milliseconds, from `turns.jsonl`)

Reliable only for turns #7-#14 (rows 10-19), where the transcript and the reply were logged in the
same row. For turns #1-#6 the row pairing is wrong, so only the per-stage values taken from the
matching rows are shown.

| Stage | Values |
|---|---|
| end-of-speech -> final transcript (13 rows with both) | 608 to 2425, mostly 600-800 |
| final transcript -> reasoning done, turns #1-#6 | 8.7, 14.4, 20.1, 12.3, 10.3, 8.7 s (backlog: calls were queued) |
| final transcript -> reasoning done, turns #7-#14 | 6.4, 6.4, 6.4, 4.5, 4.5, 6.4, 4.5, 6.7 s |
| reasoning done -> agent speaking (TTS) | 2454 to 3976, mostly ~2500-2900 |
| end-of-speech -> agent speaking, rows 10-19 (n = 8) | 7659, 7743, 7815, 9622, 9666, 9675, 9735, 9909; **median 9644 ms** |

A direct timing of one `/turn` call after the test: `http://localhost:8001` 2473-4370 ms,
`http://127.0.0.1:8001` 368-460 ms. A single turn makes four localhost hops (voice-agent to
reasoning, then reasoning to core-api three times), so about 2 s per hop explains the ~6.4 s.

## Findings

1. **Replies were late, not only wrong.** Reasoning took 4.5-6.7 s per turn because `localhost`
   costs about 2 s per connection on this machine. Turns queued up, so the first replies arrived
   9-20 s after the speech and Arjun appeared to answer the previous sentence. The rules themselves
   are fast (replay of all 14 turns is instant). (d)
2. **The turn log pairs replies with the wrong transcript** for rows 1-9 (rows 5 and 9 have a reply
   and no transcript; row 7 has a reply that was produced before its own transcript arrived).
   Recorded `eos_to_audio_ms` for those rows is not trustworthy. (d)
3. **The reminder was saved at the wrong time** (see above). (a)+(d)
4. **Companion replies are canned and rotate**, so any open conversation gets off-topic answers
   such as "ते कोणासोबत होतं?". Expected without Evon; needs an LLM or fewer, safer fixed replies. (b)
5. **The voice-agent log stopped at 13:06:55**, when the session was created, so it holds no
   STT/TTS lines for the session and cannot show Gnani errors. No error appears in the reasoning or
   core-api logs, and no `turns.jsonl` row has an error field. (d)

## Caveats

- n = 14 turns, one speaker, one session. A smoke test, not an accuracy measure.
- "end-of-speech" comes from the VAD and includes the silence wait. "Agent speaking" is playout start.
- Intent and source were replayed offline from the logged transcripts (Evon off), not logged live.
- Several verdicts depend on what was actually said; only the doctor sentence and "हो" are known.
  Real transcripts are saved in `eval/private/` (git-ignored), with `intent: null` where the
  speaker still has to say what they meant.
- Gnani credits used: not yet provided.

## Fixes made after this test (same day; the retest has NOT been run yet)

- `localhost` -> `127.0.0.1` for every service URL. Measured one `/turn` round trip, 5 runs each: median
  2334 ms before (4509, 2376, 2299, 2334, 2311), 351 ms after (740, 311, 334, 351, 449).
- Never-guess guard, Marathi/Hindi hour words, new readback wording, greeting, hearing check, correction
  of a pending reminder, "उद्या काय आहे", turn-log pairing by transcript, outdated replies not spoken,
  and a direct voice-agent file log. Each has tests; none has been tried on real speech yet.
  Stale-reply rule: only plain care and companion replies may be skipped; safety replies and replies that ask
  a yes/no are always spoken (a test per case, plus a reasoning invariant that every pending action is flagged).
- TTS probe (this laptop, 3 runs each, "आज तुमच्यासाठी कोणतीही आठवण नाही.", timbre-v2.5 / Omkar / mr-IN):
  WebSocket connect 868-1194 ms then first audio 271-291 ms after send; SSE first audio 286-356 ms
  (pooled connection); REST whole reply 540-916 ms. About 9 short TTS calls were spent on this probe.

## Retest after latency + parser fixes (2026-10-24, 13:59-14:01 IST)

**Setup.** LiveKit Console session, room `console-3de35459`, job `AJ_rU5PaSysbNLR`, worker `agent_name:
"arjun"` (dispatch worked). Code at commit `7e6b9fd`, stack restarted 13:57 with `scripts/dev-up.ps1`.
Prisma STT `mr-IN` streaming, Timbre `timbre-v2.5` / `Omkar`, Evon OFF (rules only), one speaker. Quiet room
was not restated for this session. Credits used: **not provided yet**.

**Sample.** n = 5 turns, all complete (a transcript, a reply and audio each), 0 skipped as stale, 0 dropped
rows. Every reply was reproduced exactly by replaying its transcript through the real `TurnEngine`
(intent and source below come from that replay, because reasoning does not log them; source is `rules`
for all five, Evon being off). The turn log now pairs transcript, reply and audio correctly.

| # | Prisma transcript | What was said | Intent | Mode | Arjun's reply | eos->final | final->reasoning | reasoning->audio | eos->audio (ms) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | नमस्कार | "नमस्कार": exact | GREETING | care | नमस्कार! मी ऐकतोय. सांगा, काय मदत करू? | 708 | 3776 | 2032 | 6516 |
| 2 | आज काय आहे | "आज काय आहे" (script): exact | LIST_TODAY | care | आज तुमच्यासाठी कोणतीही आठवण नाही. | 703 | 441 | 1017 | 2161 |
| 3 | उद्या सकाळी दहा वाजता डॉक्टरांकडे जायचं आहे आठवण कर | script: "...डॉक्टरकडे जायचं आहे, आठवण कर": minor difference (डॉक्टरांकडे vs डॉक्टरकडे) | CREATE_REMINDER | care | उद्या सकाळी 10:00 वाजता आठवण ठेवू का: डॉक्टरांकडे जायचं? हो किंवा नाही सांगा. | 1061 | 66 | 1721 | 2848 |
| 4 | हो | "हो": exact | CONFIRM_YES | care | ठीक आहे, आठवण नोंदवली. | 793 | 2273 | 1108 | 4174 |
| 5 | उद्या काय आहे | "उद्या काय आहे": exact | LIST_TODAY (tomorrow) | care | उद्या तुमच्याकडे: सकाळी 10:00 वाजता डॉक्टरांकडे जायचं. | 695 | 2368 | 1510 | 4573 |

"What was said": turns 2-4 from the script given before the first test; turns 1 and 5 confirmed by the speaker
afterwards. No WER is computed (EULA clause 16).

**Doctor reminder: saved correctly.** `GET /users/1/reminders` returns

    id 2  task: "डॉक्टरांकडे जायचं"  due_at: 2026-10-25T10:00:00  status: pending

That is tomorrow at 10:00 (the first test saved 07:00). No pending action is left.

**Latency.** Median end-of-speech -> agent speaking: **4174 ms** (sorted: 2161, 2848, 4174, 4573, 6516;
n = 5). The first test's median was 9644 ms (n = 8), but the sentences differ and both samples are tiny.
Reasoning -> audio (mostly the Gnani TTS WebSocket) was 1017-2032 ms, against 2454-3976 ms before.
Final -> reasoning ranges from 66 to 3776 ms: it includes the wait for the end-of-turn decision (endpointing
1.0-3.0 s, still a placeholder) plus the reasoning call itself, which measured about 0.3 s when timed directly.
The per-turn reasoning round trip is not logged separately yet.

**Errors.** No `ERROR`, `session error`, `TTS failed` or stale-drop line in `logs/voice-agent.app.log`
during the session: no Gnani STT/TTS errors were seen.

**Caveats.** n = 5, one speaker, one session: a smoke test, not an accuracy or latency benchmark.
End-of-speech comes from the VAD and includes the silence wait; "agent speaking" is playout start.
The stale-reply rule and the Marathi hour words beyond
"दहा" were not exercised by this session.

## T6 build check (2026-10-24, no browser, no speech from a person)

A LiveKit Python client played the elder: token from `/core/livekit/token` through the Vite proxy (HTTP 200),
joined a fresh room, the agent `arjun` was dispatched, and tapped text on `lk.chat` produced these attribute
changes with the agent going to `speaking`: doctor sentence -> `confirm`, "हो" -> `saved` (the reminder was
created, then deleted by hand), emergency sentence -> `safety`, companion sentence -> `story`, "नमस्कार" -> `reply`.
Token request to agent listening: 7.3 s, 3.5 s, then 1.8 s (the first two on a freshly started worker).
Tapped turns log `source: tap`, reasoning round trips of 83-933 ms, reasoning -> audio 1.3-1.6 s.
n = a handful of taps: a plumbing check, not a speech test. Gnani credits: a few short TTS replies, not read from the dashboard.

## T6 hand test in a browser (2026-10-24 evening), reported by the speaker

System-level observations only, no accuracy numbers. Setup: elder page in a browser on the laptop, Gnani Prisma and
Timbre over LiveKit, one synthetic user.

| Item | Result | Evidence |
|---|---|---|
| 10:00 confirm card for the doctor reminder | showed (speaker, browser) | the 17:15:30 turn read back "उद्या सकाळी 10:00 वाजता आठवण ठेवू का: ..." |
| A spoken "हो" saved the reminder | reported yes by the speaker | **NOT corroborated**: see below |
| Tap हो/नाही, 10 s dashboard refresh, red emergency banner, 112 button, Wi-Fi retry screen, live transcript, Omkar voice quality | not verified | none yet (T8 hand-test checklist) |

What the logs show for that session: the "हो" at 17:15:45 came back from Prisma as a 24-word repetition artifact, was
read as a story, and the pending reminder was REJECTED (not saved). That failure led to fixes A to F. The only saved
doctor reminder (id 2) came from the 14:00 Console session. After the 21:14 database cleanup there is no action row,
no new reminder and no voice turn in `turns.jsonl` from a later browser session, so the post-fix "spoken हो saved it"
is recorded here as the speaker's report and is to be re-checked with log evidence in the T8 session.

## Regression suite (text only, synthetic)

core-api 54, reasoning 221, voice-agent 32, scheduler 3, vitest 13 passed; ruff clean; web `tsc` clean; eval 42/42
intent, 12/12 slot, 5/5 distress (2026-10-24, Windows, Python 3.12). These are regression checks on
synthetic text, not accuracy on real speech.
