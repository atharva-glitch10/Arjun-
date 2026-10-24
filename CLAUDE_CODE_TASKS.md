# Arjun — Work Order for Claude Code (Oct 21 → Nov 8, 2026)

Read `CLAUDE.md` first. It is the source of truth for product rules and hard boundaries.
This file is the task list and the order to do it in. Today is 2026-10-21. Final submission
is Nov 8 (contest deadline Nov 10, 23:59 IST, no extensions). Main public demo post: Nov 1.

## How to work (follow every time)

1. **One task at a time, in order.** Do not start a task while the one before it is unfinished,
   unless I say so. Use plan mode for anything touching more than 2 files: show the plan, wait
   for my OK.
2. **Feature freeze.** Do NOT build anything not listed below (no BP/sugar, meals, export,
   strip photos, RSS, full RAG, login/roles, migrations, nginx replicas, S3 cache, multi-elder).
   If you think something is needed, ask me first.
3. **"Done" means verified.** For each task, run the acceptance check and paste the actual
   output (test results, log lines, commands). Never mark a task done from reading code alone.
   If you could not verify something, say exactly what and why.
4. **Commit after every task** on `main`, with a clear message. Run `git status` first and make
   sure `.env` and any secret are never staged.
5. **Secrets.** Never print, echo, log or paste the values in `.env`. Refer to variables by name
   only. If a command would print a secret, don't run it. Never put a secret in frontend code.
6. **Never invent numbers.** Latency, accuracy and credit cost are only reported if measured.
   Write measured results to `eval/results/RESULTS.md` with date, method and sample size.
7. **Stop and ask me** at every point marked 🛑. Those need me (keys, dashboards, my voice,
   decisions, other people).
8. **When stuck for more than ~20 minutes** on the same error, stop, summarise what you tried,
   and propose the fallback listed in the task.
9. At the end of each work session, update `STATUS.md`: done / in progress / blocked / next.

---

## P0 — Today and tomorrow (Oct 21–22). Nothing else until P0 is done.

### T1. First commit
- Make sure `.gitignore` covers `.env`, `*.env`, `.venv/`, `node_modules/`, build outputs,
  any audio recordings, and `eval/private/`.
- Create the first commit on `main`.
- **Accept:** `git log --oneline` shows the commit; `git ls-files | grep -i env` shows only
  `.env.example` (if any). Paste both outputs.

### T2. Key rotation support 🛑
- I will rotate the Gnani key and LiveKit key/secret in their dashboards myself and update
  `.env`. You do not touch the values.
- Your part: add `.env.example` listing every variable name the project reads (no values), with
  a one-line comment per variable.
- **Accept:** `.env.example` committed. After I say "keys rotated", restart the agent and paste
  the "registered worker" log line (no secrets in it).

### T3. Move the launch script into the repo
- Move `run-agent.ps1` out of your scratchpad into `services/voice-agent/run-agent.ps1`
  (or replace it with `python-dotenv` loading the root `.env` inside `agent.py` — pick one,
  tell me which). It must load only the variables the agent needs.
- Add `scripts/dev-up.ps1` (or document in README) showing how to start: core-api, reasoning,
  voice-agent, web — in that order.
- Update `CLAUDE.md`: the project uses ONE root `.env`.
- **Accept:** from a fresh PowerShell window, the documented command starts the agent and
  it registers. Paste the commands and the log line.

### T4. First live voice test 🛑
- Generate a LiveKit access token for room `arjun-test`, identity `aaji-test`, valid 1 hour,
  using the LiveKit server SDK (not printed anywhere except to me once). Tell me exactly how to
  join with the LiveKit Agents Playground.
- Make sure the agent logs, per turn: transcript text, detected/selected language, and
  timestamps for (a) end of user speech, (b) final transcript, (c) reasoning response,
  (d) first TTS audio frame. Log to stdout AND append one JSON line per turn to
  `eval/results/turns.jsonl` (no audio, no secrets).
- I will speak: "आज काय आहे?", "उद्या सकाळी दहा वाजता डॉक्टरकडे जायचं आहे, आठवण कर", "हो".
- **Accept:** paste the 3 transcripts as Prisma returned them, and per-turn latencies.
  Then write to RESULTS.md: did Marathi streaming STT work (yes/no), transcripts vs what I said,
  end-of-speech→first-audio latency per turn. Ask me how many credits the dashboard shows used.

### T5. Fallback if Marathi streaming STT fails (only if T4 fails on STT)
- First confirm from Gnani docs (docs.gnani.ai) which language codes streaming supports, and
  which REST supports. Quote the doc lines.
- Implement push-to-talk: elder taps बोला, records until tap/1.5 s silence, sends the clip to
  REST STT (`POST https://api.vachana.ai/stt/v3`, `X-API-Key-ID` header, clips ≤ 60 s per docs).
  Keep TTS via Timbre.
- **Accept:** one recorded Marathi sentence returns a correct transcript and a spoken reply.

---

## P1 — Core demo (Oct 23–27)

### T6. Elder app talks through LiveKit + Gnani (remove browser speech) — HIGHEST P1
Reason: the demo must use genuine Gnani speech. Browser SpeechRecognition / speechSynthesis must
not be used anywhere in the elder app.
- core-api: add `POST /livekit/token` that returns a short-lived token for the elder's room,
  signed server-side with `LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET` (python `livekit-api`).
  Room name per elder (e.g. `elder-<id>`). Secret never leaves the server.
- web elder app: use `livekit-client` (or `@livekit/components-react`) to join the room when
  Aaji taps बोला; publish mic; play the agent's audio track. Disable frontend noise suppression
  if agent-side BVC is used (no double processing). BVC is not in the code yet, so the browser's own
  echo cancellation + noise suppression stay on.
- Screen states (home → listen → confirm → saved) must follow what the agent is doing. Send
  state from the agent to the app with LiveKit data messages or participant attributes
  (choose one, explain why). The screen mirrors what Arjun says; voice and tap both work.
- Delete or hard-disable all browser speech code paths. Grep to prove it.
- **Accept:** on my phone/laptop browser: tap बोला → speak Marathi → Gnani transcript in agent
  log → Timbre voice reply → screen shows confirm card. Paste the grep proving no
  `SpeechRecognition`/`speechSynthesis` remains.

### T7. Voice reminder end to end
- Flow: speak reminder → agent reads back date/time ("उद्या सकाळी १०:००, डॉक्टरकडे. बरोबर?")
  → "हो" → core-api saves via propose/confirm/execute → family dashboard shows it.
- Ambiguous AM/PM or date → ask, never guess. "नाही" → re-listen.
- Clean up task text (today it's leftover words like "doctor jaycha"): produce a short clean
  phrase ("डॉक्टरकडे जाणे"). Rules first; Evon only if available.
- **Accept:** 5 runs in a row, by voice only, each creates the correct reminder. Log each run
  in RESULTS.md (what I said, what was saved, pass/fail).

### T8. Scheduler → spoken delivery (reminders + medicines only)
- Today the scheduler only logs. Make due reminders and medicine prompts reach the elder's
  voice session and be SPOKEN, and show the matching screen (Reminder / Medicine).
- Constraint: browsers block audio until a user gesture. Design for a dedicated, always-open
  elder device that was tapped once ("Start Arjun" screen). If no session is open when a
  reminder is due, queue it and deliver when the session opens; tell the family dashboard it
  was not delivered on time.
- Medicine text comes verbatim from SQL via a fixed template. Never LLM-generated.
- "घेतली" / "नंतर" by voice or tap update status. Not confirmed after N reminders (config) →
  family notified (dashboard alert is enough).
- Add scheduler tests (due-time selection, snooze, missed escalation, no double-firing).
- Briefings and openers: NOT in this task.
- **Accept:** a reminder set 2 minutes ahead is spoken on the elder device; a medicine prompt
  is spoken, "घेतली" marks it taken on the dashboard. Tests pass (paste output).

### T9. Evon decision support 🛑 (by Oct 24)
- I will decide: (a) rented GPU running vLLM, or (b) no Evon for the demo.
- If (a): I'll give you `EVON_BASE_URL`, `EVON_API_KEY`, `EVON_MODEL`. Verify with
  `GET /v1/models`. Always send `"chat_template_kwargs": {"enable_thinking": false}`.
  Run the existing intent eval AND 20 new Marathi sentences I provide through Evon. Report
  JSON validity %, intent accuracy %, median latency. Compare temperature 0 vs 0.6 on the same
  set, then fix the value in config and record why in RESULTS.md.
  Verify boundary 8 (no facts/recipes from model memory) with 10 adversarial prompts.
- If (b): companion replies stay rule-based; write that decision into CLAUDE.md and make sure
  nothing claims Evon was used.
- Either way, the app must keep working with `EVON_BASE_URL` empty.

### T10. Physical emergency handling
- Add an EMERGENCY path in the distress check, above everything: phrases like
  "छातीत दुखतंय", "श्वास घेता येत नाही", "पडले", "चक्कर येतेय", "खूप दुखतंय" (and Hindi/English
  equivalents). Response: short, calm, fixed template: tell her to call 112 / ask someone near,
  immediately alert the configured family contact, never continue chatting, never diagnose.
- Keep the existing emotional distress path (Elderline 14567, family per consent).
- Both paths must work with Evon off (rules).
- **Accept:** tests for each phrase pass; a test proves emergency overrides an in-progress
  reminder flow. Mark clearly in code and README that the lexicon awaits native-speaker review.

### T11. Minimal "last story" callback
- When companion mode starts, if a previous story exists for this elder, Arjun may say one
  short callback using ONLY stored summary text: "मागच्या वेळी तुम्ही <title> बद्दल सांगितलं होतं.
  आज पुढे सांगाल का?" If no story or low confidence, ask openly instead. Never invent.
- Private stories stay private; this callback is only spoken to the elder.
- No pgvector/RAG in this task.
- **Accept:** tests: with a stored story → callback uses its title verbatim; with none →
  neutral opener; "he visar" deleted story → never mentioned.

---

## P2 — Evidence & safety (Oct 27–30)

### T12. Distress / emergency test set from outside 🛑
- Create `eval/distress_external.csv` with columns: phrase, expected (EMERGENCY/DISTRESS/NONE),
  source. I will fill it with 20+ phrases written by a native speaker (not by you).
- Run it; report misses honestly. Fix rules only by adding general patterns, not by copying
  each test phrase (no overfitting). Re-run and report.
- **Accept:** results table in RESULTS.md. The demo gate passes only if every EMERGENCY and
  DISTRESS phrase is caught; false alarms are listed.

### T13. Real-user test kit 🛑
- Write `eval/USER_TEST.md`: a 10-minute script for testing with a consenting elder using only
  synthetic tasks (set a reminder, ask today's schedule, confirm a medicine, tell a short
  story, say "he visar"). Include a consent line to read aloud and a results sheet.
- Make `turns.jsonl` capture per-session pass/fail of each task.
- After I run sessions, compute: task success rate, median end-of-speech→first-audio latency,
  number of re-asks per task. System-level numbers only (not Prisma WER — EULA clause 16 is
  unresolved).
- **Accept:** script committed; after my sessions, numbers written to RESULTS.md with n.

### T14. Demo-ready deployment
- Production build for web (no Vite dev server in the container).
- Decide and document how the demo runs: laptop + tunnel, or a small cloud VM. Explain the
  trade-off, recommend one, wait for my OK 🛑.
- **Accept:** elder app opens on my phone over the internet, joins LiveKit, Arjun speaks.

### T15. Docs truth pass
- Update README test counts, feature status (built / not built / frozen), how to run, and the
  architecture diagram so they match reality. Update CLAUDE.md: one root `.env`, frozen list,
  Evon decision, emergency path.
- **Accept:** every number in README matches a command you ran today (paste them).

---

## P3 — Demo & submission support (Oct 30–Nov 8)

### T16. Demo script and seed data
- `demo/seed.py`: loads synthetic data only (Aaji, Rahul, Neha, made-up medicine names
  "Medicine A/B", sample story). No real names of my family, no real medicines.
- `demo/SCRIPT.md`: the 60-second flow (problem → voice reminder + dashboard updates →
  "शिकवा ना" recipe moment → Memory Book share → closing line naming the Gnani models used),
  plus a 2–3 minute version. Each step lists exactly what to say and what should appear.
- Rehearsal check: run the full 60 s flow 3 times; list any failure.

### T17. Write-up draft
- `SUBMISSION.md`: problem, users, how it works, which Gnani models/APIs are used and where
  (Prisma, Timbre; Evon only if T9 = a), safety design, measured results from RESULTS.md only,
  limitations (honest), next steps (the frozen list), each member's contribution (🛑 I fill).
- No claims that aren't backed by RESULTS.md or code.

### T18. Interview prep notes
- `docs/ARCHITECTURE_WALKTHROUGH.md`: one page per service — what it does, key decisions and
  why, how a voice turn flows end to end, what fails and how it's handled. Written so I can
  explain it without notes.

---

## Reporting format (end of every task)

```
TASK: T#
STATUS: done | blocked | partial
CHANGED: files
VERIFIED BY: commands/tests run + pasted output (no secrets)
MEASURED: numbers, or "none"
OPEN ISSUES / RISKS:
NEXT:
```

Start with T1. Show me the plan for T1–T3 first.
