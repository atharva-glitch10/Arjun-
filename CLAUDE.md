# CLAUDE.md - Arjun project spec and hard boundaries

Arjun is a voice companion that helps elderly Indians (Marathi / code-mixed / Hindi / English) manage
their day and share life stories by talking. Two halves: a **reliable assistant** (reminders, schedule,
medicines, help) and a **warm listener** (stories, interests, Memory Book).
Principle: **Arjun is a bridge to people, not a replacement for them.**

## Contest (Gnani AI "Great Indian AI Internship Challenge")
- Deadline 2026-11-10 23:59 IST, no extensions. **We submit by Nov 8; main demo post ~Nov 1.**
- Must genuinely use Gnani models/APIs. A demo whose voice is NOT Gnani's (browser speech) is a
  misleading demo, which the rules forbid. The elder app must speak through LiveKit + Gnani (T6).
- Shortlist = verified engagement on public LinkedIn/X posts (#GnaniAI #GreatIndianAIInternshipChallenge);
  offers = individual interviews. No bought engagement, engagement swaps, plagiarism.
- No real phone numbers, Aadhaar, PAN or recorded calls. Synthetic demo data only.
- Gnani EULA clause 16 may forbid publishing benchmark results: report **system** results
  ("8/10 reminders set correctly"), not Prisma WER, until Gnani confirms.
- Target award: Main Character (regional language); backup Real Deal. Only one can be won.

## Hard boundaries (never violate, never "improve" away)
1. **The LLM never touches the database.** The LLM only suggests; core-api validates and acts.
   Flow: reasoning proposes -> core-api validates and stores the action -> it is executed.
   **CHANGED 2026-10-31 (team decision): no yes/no questions.** Arjun executes at once, reads it back in ONE
   line ("ठेवली: उद्या सकाळी 10:00, डॉक्टर. बदलायचं असेल तर 'नको' म्हणा.") and "नको / चुकलं" within the undo
   window (reasoning 150 s, core-api 180 s) puts it back (`POST /actions/{id}/undo`). Missing details are still
   ASKED (boundary 3). A help request cannot be unsent; undo sends the family a second note instead.
   `ARJUN_ASK_BEFORE_ACTING=1` restores the old spoken-yes flow (the older test suites run in that mode).
2. **Reminders, appointments, medicines, contacts come from SQL only.** RAG is for past stories only.
3. **Never guess.** Ambiguous AM/PM, missing date, or "after the meal" without which meal -> ask.
4. **Arjun is an AI.** Say so whenever asked. Never claim to be human, to have feelings or family.
5. **No medical advice**, diagnosis or medicine decisions. Only read back reminders the caregiver set.
6. **Medicines**: only the family creates/edits them (dashboard), never by voice, never the LLM.
   Name + dose + timing are read EXACTLY as entered, via a fixed template from SQL (never
   LLM-paraphrased or translated). Never answer skip / double / late / purpose / side-effect /
   missed-dose questions -> "हे डॉक्टरांना विचारा. <family name>ला कळवू का?" Never say "take the
   missed dose" or "take two". Not confirmed after N reminders -> notify family only. "Taken" is
   self-reported; label it so. No adherence scores, streaks or guilt.
7. **Health readings (BP/sugar, frozen for now)**: if ever built, never say a reading is good, bad,
   high, low or normal; repeat numbers back for confirmation; show raw values only.
8. **Safety checks run first on every turn**, rules only, and work with core-api and the LLM down:
   - **Physical emergency** (chest pain, can't breathe, a fall now, fainting, bleeding) -> fixed
     template: call 112 / call out to someone near; try to alert family. Never diagnose, never
     continue chatting. **DECIDED 2026-10-24: an emergency ALWAYS alerts the family, even when
     distress-alert consent is off.** The alert is a prominent dashboard banner (a notification of kind
     "emergency") that names the configured family contacts. It is a dashboard alert ONLY: no call, SMS or
     WhatsApp is sent (telephony is frozen), and the alert text says so (boundary 14).
   - **Emotional distress** -> stop the story, respond gently, offer a family call, mention
     Elderline 14567 (8 AM-8 PM), alert caregiver ONLY per consent (unchanged).
   - **Family view (2026-10-31)**: per conversation a seriousness level (normal / watch / urgent / emergency),
     a mood word and a short paraphrased summary go to the dashboard (`wellbeing` table + live feed). NEVER a
     transcript. Mood, summaries, distress and loneliness are shown ONLY with the same consent flag
     (`consent_distress_alert`, labelled "share how she is doing"); without it the family sees what she did and
     the level for help requests / emergencies only. The LLM may RAISE the level, never lower the rules floor.
   - Both lexicons are UNVERIFIED until a native speaker reviews them. The external distress test
     set (T12) must pass before any public demo.
9. **No engagement tricks**: no streaks, no "I missed you", nothing discouraging human contact.
10. **Companion never recites recipes/facts from model memory.** It asks the user to teach it.
    At most one opener per day window; "nako" means no more that day.
11. **Stories are private by default**; (2026-10-31: kept privately without asking; shared only when she asks,
    "हे घरच्यांना सांग";
    "he visar" deletes. Never invent memories: reference a past story only from stored text.
    No raw audio stored. Demo uses synthetic data only.
12. **Secrets**: ONE root `.env` (only `.env.example` is tracked). `LLM_API_KEY` is read only by reasoning. `GNANI_API_KEY` and LiveKit keys
    are read only by voice-agent (it loads just `GNANI_*`/`LIVEKIT_*`/`ARJUN_*`) and by core-api's
    future LiveKit token endpoint. Never in React code, never in Git, never logged, never printed.
    `CORE_API_KEY` is required: core-api refuses to start without it (tests use ARJUN_TESTING=1).
13. **Never invent numbers.** Report only what was measured, in `eval/results/RESULTS.md`.
14. **Never claim delivery that didn't happen.** Until T8, reminders/medicine prompts/openers are
    only logged by the scheduler, not spoken. "fired" means "due time passed".

## Models (Gnani)
| Model | Role | Access |
|---|---|---|
| Prisma | STT, ears (streaming, code-mixed) | Gnani API via LiveKit Gnani plugin (credits) |
| Timbre | TTS, Arjun's male voice | Gnani API via plugin. API accepts ONLY `timbre-v2.5` / `timbre-v3.0` and needs a voice (we use `Omkar`, verified 2026-10-21) |
| Hosted LLM (**non-Gnani**) | Open conversation ONLY: companion/chat replies, and turns the rules cannot read (UNKNOWN) | Any OpenAI-compatible API: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_PROVIDER_NAME` (key read only by reasoning). What the elder says in those turns is sent to the provider, so demo data is synthetic. Limits: ~4 s per turn, 80 tokens (2026-11-02; measured: Marathi replies use 20-42), last 8 exchanges |
| Evon v3.3 | NOT USED (decision T9, 2026-10-24) | Not on the API platform, not covered by credits; would need an 80 GB GPU. The `EVON_*` names still work as aliases of `LLM_*` if it is ever used. Never run it on the dev laptop |

**Truthful write-up:** speech in = Gnani Prisma, speech out = Gnani Timbre, the conversation LLM = the hosted non-Gnani provider named in `LLM_PROVIDER_NAME` (none configured yet), Evon = not used.

**LLM (2026-10-31): Sarvam-105B** (hosted, non-Gnani) via `SARVAM_API_KEY` (alone enough; `SARVAM_MODEL`
optional, e.g. `sarvam-105b-conversations`). Thinking is OFF (`reasoning_effort: null`) for latency and any
`<think>` text is stripped. It may put ONE Timbre v3.0 voice tag (`<laugh> <giggle> <sigh> <exhales> <whispers>
<excited> <slow> <pauses>`) in a companion reply; the screen never shows tags, and non-v3 TTS gets them stripped.
It also writes the family's conversation summary (JSON, enums validated). Calls are limited (concurrency 4,
60/min, back-off after a provider 429) and never queue: over a limit, the rules answer.

Layered brain so the app works with no LLM at all: safety rules -> ONE LLM understanding call for every non-safety
turn (intent, slots, reply, confidence) -> the rule parser ONLY as a fallback when that call times out, errors,
returns bad JSON or reports confidence < 0.4 for an action. Action intents still execute the deterministic SQL-backed
paths, so the model chooses the meaning and the code decides the action; a chat reply can never invent a reminder or
a medicine record. Deterministic state answers (pending yes/no, stop, medicine taken, time/next-up, greeting, hearing
check) stay in code. Care mode, times, medicines, confirmations and safety never wait for the LLM.
Understanding temperature: 0. Companion: 0.5 since 2026-11-04 (was 0.3, 0.6 before that), chosen by the 50-turn
companion eval, not by feel. Send `chat_template_kwargs` only to vLLM/Evon (`LLM_SEND_TEMPLATE_KWARGS=0`
for hosted providers).

## Voice path facts (verified)
- LiveKit Agents **1.8.6** (pinned). The worker registers as `agent_name="arjun"` and joins ONLY
  rooms that dispatch it explicitly. `scripts/make_token.py` adds that dispatch to the token's room
  config; dispatch happens when the room is created, so each test uses a fresh room name.
  The LiveKit Console with "No agent selected" never dispatches our agent.
- A reasoning failure must never mean silence: `bridge.reply_or_fallback` speaks a fixed line.
- Browsers block audio until a tap: proactive speech needs a dedicated, always-open elder device.

## Architecture
```
Elder device (React, one big button) -> LiveKit room -> voice-agent (Python worker, "arjun")
  (no noise cancellation yet, open question 6) -> Prisma STT -> reasoning /turn (emergency -> distress -> router -> rules -> hosted LLM for chat / UNKNOWN only)
  -> core-api (FastAPI, Postgres/SQLite) -> reply text -> Timbre TTS -> speaker
scheduler: due reminders, medicines, briefing, openers (logged only until T8).
Dashboard: React + TS -> core-api (via dev proxy; production needs a real proxy, T14).
```
Services: `services/core-api`, `services/reasoning`, `services/scheduler`, `services/voice-agent`,
`web/`, `shared/schemas`, `eval/`, `design/` (UI reference only). Start locally with
`scripts/dev-up.ps1`.

## Elder UI: "Ghar" design system
Tokens: `web/src/styles/tokens.css` (source of truth). Khadi ground, indigo primary, haldi accent
(dark text only), kumkum = help only, leaf = success. Tiro Devanagari Marathi headings + Mukta body.
Rules: tap targets >= 14 mm (80-92 px buttons), elder text >= 24 px, contrast >= 4.5:1, icon + word
always, one decision per screen, no swipes/timeouts, everything also spoken, yes/no by voice always
works, motion off under prefers-reduced-motion.

## Scope
MVP: voice reminders, "aaj kay aahe", mark done, family-call reminders, help request, medicine
reminders (meal-anchored), story listening, interest openers, Memory Book, safety, family dashboard.
**Frozen until after Nov 10** (do not build without asking): BP/sugar readings, meal/walk check-ins,
Export for doctor, medicine-strip photos, RSS news, full pgvector RAG, login/roles, migrations,
nginx replicas, S3 cache, multi-elder accounts, telephony, SMS/WhatsApp, Evon fine-tuning.

## Open questions (unresolved; do not assume answers)
1. Does Prisma support Marathi in *streaming*? If not, push-to-talk (T5).
2. Prisma accuracy on elderly speakers? If poor: mandatory confirmation, short phrases.
3. Credit cost per call.
4. ~~Evon: GPU or not~~ DECIDED 2026-10-24 (T9): **no Evon for the demo.** The demo runs on rules + Marathi time grammar only (EVON_BASE_URL empty, rule-based fallback). Revisit only after Nov 10 or if a GPU becomes available.
5. Discord: is a non-Gnani LLM allowed in the entry? (Used anyway for open conversation per the team decision of 2026-10-24; Gnani remains STT + TTS. Disclose it in the posts; ask on Discord.) Also: Consenting relative in demo video? Publishing accuracy
   numbers (EULA 16)? Teammate using the primary registrant's key?
6. Does noise cancellation (LiveKit BVC) help or hurt Prisma (A/B)? It is NOT in the code yet (the plugin
   needs PyPI); the elder browser keeps its own echo cancellation + noise suppression on until then.
7. Endpointing is mode-aware (care 0.8 / 2.5 s, chat 1.6 / 4.0 s, 2026-10-31) and a sentence ending in आणि/पण/म्हणजे/की is held; all are placeholders; tune on elderly speech.
8. ~~Emergency alert: should it override the family-alert consent setting?~~ DECIDED 2026-10-24: yes for a
   physical emergency (always alerts); no for emotional distress (consent only). See boundary 8.

## Working rules for Claude
- Follow `CLAUDE_CODE_TASKS.md` (if present): one task at a time, feature freeze, verify, commit.
- Tests: `pytest` in `services/core-api`, `services/reasoning`, `services/voice-agent`,
  `services/scheduler`; `ruff check .` at root; `npx tsc --noEmit` in `web`;
  `python eval/run_eval.py`. Run them after changes.
- Don't claim something works unless it was run. Mark unverified code as unverified.
- Keep care-mode and safety replies as fixed templates; never route them through a free-form LLM.
- Update README "Known limitations" and STATUS.md when behaviour or verification status changes.
