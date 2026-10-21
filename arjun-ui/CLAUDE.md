# Arjun — Voice Care Companion for Elderly Indians

Product and assistant persona are both "Arjun" (male Timbre voice). Arjun introduces itself as an AI.
Contest: Gnani AI "Great Indian AI Internship Challenge". Deadline 2026-11-10 23:59 IST, NO
extensions; we submit by 2026-11-08. Solo or team of two; one entry; demo must be public on
LinkedIn/X with #GnaniAI #GreatIndianAIInternshipChallenge before submitting. Shortlist = verified
engagement; offers = individual interviews. No bought engagement, engagement swaps, plagiarism or
misleading demos. Gnani may change rules anytime — re-check gnani.ai/internship weekly.

## What we are building
Core idea: Arjun is a **bridge to people, not a replacement for people.**
Native-language-first (Marathi + code-mixed) voice companion. Elder talks; family configures via
a web dashboard. Target awards (only one can be won): Main Character (regional language), backup
Real Deal.

1. **Care mode** — "the AI suggests, the system verifies, the user confirms. Never guess."
   Reminders by voice (confirm before saving), "Aaj kay aahe?", mark done, family-call reminders,
   help request → caregiver alert, morning briefing, **medicine reminders** anchored to meal times
   ("after lunch" = lunch time + family-set offset), **walk/activity reminders**.
2. **Companion mode ("Kahani")** — listen more than talk; short warm replies, follow-up questions,
   no advice. **Interest openers ("Shikva na")**: from a family-set interest profile, Arjun asks
   the USER to teach ("Aaji, aaj dhapate karayche ka? Tumchi recipe mala shikva na?"). Arjun never
   supplies recipes, facts or news from model memory. Max one proactive opener per window, only
   in family-set hours; "nako"/"aaj nahi" ends it for the day.
   **Memory Book**: stories/recipes shared with family ONLY after explicit spoken consent.
3. **Health routine** — meal check-ins at family-set meal times ("जेवण झालं का?"), medicine and
   walk confirmations, and **BP / sugar check reminders ONLY if the family enables them on the
   doctor's advice** (sugar only if diabetic). Aaji reads numbers aloud → Arjun repeats them back
   ("१४२ बाय ८८, बरोबर?") → saved only on "हो". Numbers parsed by rules + confirmation, never
   guessed by the LLM.
4. **Family dashboard** — today timeline (meals, medicines, walk, checks, calls with status),
   summary tiles, 7-day grid (on time / late / not confirmed; "on time" = within a family-set
   window, default 30 min), health-check log + "Export for doctor", routine, interests, chat
   hours, help alerts, shared Memory Book only.

Lower priority (only after MVP works): water reminders (amount set by family/doctor),
"where did I keep it?" voice notes (repeat only what she said), family birthdays/festivals,
doctor-visit checklist, medicine refill reminders,
interest news from a fixed RSS allow-list (summarise only fetched text, name the source, never
health news). Out of scope: telephony, SMS/WhatsApp, fine-tuning Evon.
Never build: medical Q&A, fall/emergency detection, banking/payments.

## Hard boundaries (never violate)
- No medical advice, diagnosis, or medication decisions. Not therapy; never claim to treat
  loneliness/depression. No fall/stroke/emergency detection claims.
- **Medicines**: ONLY family creates/edits them (dashboard) — never Aaji by voice, never the LLM.
  Name + dose + timing read EXACTLY as entered via a fixed template from SQL (never LLM-paraphrased
  or translated). Never answer skip/double/late/purpose/side-effect/missed-dose questions →
  "हे डॉक्टरांना विचारा. राहुलला कळवू का?" Never say "take the missed dose" or "take two".
  Not confirmed after N reminders (family-set) → notify family only. "Taken" is self-reported;
  label it so. No adherence scores, streaks or guilt.
- **Health readings (BP/sugar)**: Arjun NEVER says a reading is good, bad, high, low or normal,
  never compares to norms, never suggests action. Family dashboard shows raw values only; a
  neutral "outside the range your doctor set" flag ONLY if the family entered a doctor's range.
  All meal/medicine/reading statuses are self-reported — label them so.
- Always says it is an AI when asked/relevant. Never claims to be human, have feelings, a body,
  a family or lived experiences.
- No engagement-maximising: no streaks, no "I missed you", never discourages human contact;
  actively nudges toward family and friends.
- Stories PRIVATE by default; family sees only explicitly shared ones. "He visar" deletes.
- Never invent memories: reference a past story only on high-similarity retrieval, else ASK
  ("Tumhi mala aadhi sangitla hota ka…?").
- Distress (hopelessness, self-harm, abuse, fear) → overrides everything: stop the flow, respond
  gently, offer to call family, mention Elderline 14567 (govt senior helpline, 8 AM–8 PM), alert
  family per consent rules. Never diagnose. Keyword check ALWAYS runs even if the LLM is down.
- LLM NEVER writes to the DB. It outputs a structured intent; backend validates; ambiguous
  actions need spoken yes/no confirmation.
- Reminders, appointments, medicines, contacts come from SQL, never from RAG or model memory.
- Synthetic demo data only: no real phone numbers, Aadhaar, PAN, recordings. Don't show a real
  relative's real medicines on camera. Never store raw elder audio (transcripts/summaries only).
- API keys only in server-side `.env` (voice-agent / services). Never in React code or Git.

## Gnani models
| Model | Role | Access |
|---|---|---|
| Prisma v2.5 (STT) | ears — streaming, code-mixed | Gnani API via `livekit-agents[gnani]`, uses 5,000 credits |
| Timbre (TTS, beta; v2.0/v2.5 selectable) | voice | Gnani API via LiveKit plugin, uses credits |
| Evon v3.3 (LLM) | brain | NOT on API platform, NOT covered by credits; self-host |

Evon: HF `gnani/gnani-evon-v3.3-30B-A3B` (weights by request; BF16, ~32B total / ~3.5B active,
128K ctx, `trust_remote_code`, supports Marathi + 10 others). Runtime vLLM >= 0.12 or SGLang on
H100 80GB / H200 / A100 (rented GPU or Friendli dedicated endpoint) → OpenAI-compatible URL in
`EVON_BASE_URL`. ALWAYS send `"chat_template_kwargs": {"enable_thinking": false}` in the live
path. Use a system prompt naming target language + script; verify output script downstream.
Tool calling is immature per Gnani → use JSON output contract + schema validation.
Dev laptop (16 GB RAM / 3 GB GPU): NEVER run Evon locally. Community GGUFs are unofficial —
use only if they pass our eval, and disclose. Turn rented GPUs off when not testing.

## Layered brain (swappable behind one interface)
`understand(text) -> intent JSON`, `reply(context) -> text`.
1. Rules: dialect normaliser, keyword intents, Marathi time grammar (sakali/dupari/sandhyakali,
   "10 vajta", meal-relative), state machine, distress keywords. Care mode runs on rules first.
2. Optional own small intent classifier (trained on our labelled Marathi/code-mixed sentences).
3. Evon: messy phrasing fallback, companion replies, story summaries, LLM distress check.
App must work with Evon off (care mode + keyword distress).

## Model settings (temperature FIXED per mode, in config, never changed at runtime)
- Extraction / distress check: 0 vs Gnani-recommended 0.6 (top_p 0.95) — compare on eval, then fix.
- Companion replies: one fixed tested constant.

## Architecture (monorepo, docker-compose)
- `web/` — React + TS (Vite). Elder voice screen (LiveKit client) + family dashboard.
- `services/core-api/` — FastAPI, single source of truth; Postgres via SQLAlchemy + Alembic.
  2 replicas behind `nginx/` (load-balancing demo).
- `services/voice-agent/` — LiveKit Agents worker; Gnani STT/TTS; BVC noise cancellation (LiveKit
  Cloud only; disable frontend NC to avoid double processing). No business logic.
- `services/reasoning/` — FastAPI: distress check → mode router → layered brain → schema
  validation; RAG over story memories (pgvector).
- `services/scheduler/` — due reminders, medicine/walk reminders, briefing, openers, alerts.
- `shared/schemas/` — JSON schemas for intents/tool calls (single source).
- `eval/` — manifests + scripts.

Data stores (one job each): **Postgres** = users, family, reminders, appointments, medicines,
activities, contacts, routine, interests, consent, escalation rules, story memories (+pgvector).
**MongoDB** = conversation event logs + eval traces (transcript, intent, mode, per-stage latency).
**S3** (one bucket) = eval audio, cached fixed-phrase TTS, Memory Book exports, medicine-strip photos.

## Intents (v1 — don't add more until reliable)
Care: CREATE_REMINDER, LIST_TODAY, COMPLETE_REMINDER, GET_APPOINTMENT, CALL_FAMILY_REMINDER,
REQUEST_CAREGIVER, CONFIRM_YES, CONFIRM_NO, MED_TAKEN, MED_SNOOZE, ACTIVITY_DONE, MEAL_DONE,
LOG_READING (bp_sys, bp_dia, pulse, sugar; always read back for confirmation),
MEDICAL_QUESTION (always deflected).
Companion: CHAT, SHARE_STORY_WITH_FAMILY, FORGET_MEMORY, DECLINE_TOPIC.
Safety: DISTRESS (every turn, overrides). Fallback: UNKNOWN. Openers come from the scheduler.
```json
{"intent": "CREATE_REMINDER", "task": "doctor visit", "date": "2026-10-14",
 "time": "10:00", "time_ambiguous": false, "confidence": 0.86, "language": "mr"}
```
- Invalid JSON/schema → retry once → rules → else ask user to repeat.
- Relative times resolve from family-set wake/meal times; unclear AM/PM → ask.
- Mid-story task request → switch to care mode, finish, offer to return to the story.

## Latency & audio
- Streaming STT/TTS everywhere; cache fixed phrases; log per-stage timestamps to MongoDB.
- Turn detection tuned for slow elderly speech; companion mode allows longer pauses. Measure.
- Browsers block autoplay: proactive speech (briefing, openers, reminders) needs a dedicated
  always-open device after one tap. Don't claim telephony unless the demo rings a phone.

## Elder UI — "Ghar" design system (Direction B; Direction A "clinical" is rejected)
- Palette: khadi ground #FBF1DE, indigo #23305E (primary, white text), haldi #F2B632 (dark text
  #2A1E14), kumkum #B3261E (help only), leaf #2F6B3A (success), muted text #5C4632.
- Fonts: Tiro Devanagari Marathi (headings), Mukta (body/UI). Devanagari copy for elders.
- Motifs: mango-leaf + marigold toran, diya = Arjun's presence, thali for meal timing, ruled
  "आजीची वही" notebook for stories, family photo avatars, time-of-day themes (morning/evening).
- Motion: breathing speak button, flickering diya while listening, gentle pop on success —
  all disabled under `prefers-reduced-motion`.
- Rules (evidence-based): touch targets >= 14 mm (we use 80–92 px buttons); body text >= 24 px;
  contrast >= 4.5:1; icon + word always; one decision per screen; no swipes/pinch/timeouts;
  every screen also spoken aloud; "yes/no by voice" always works. Family dashboard: Mukta,
  normal sizes, same palette.
- Test with real elders: diya-only speak button (no mic icon) may be unclear — keep "बोला" label.

## Our 8 concerns
Load balancing = LiveKit worker dispatch + nginx ×2 core-api. Noise = BVC, A/B vs Prisma WER.
Latency = streaming + thinking off + caching + per-stage logs. TTS/STT = Gnani via LiveKit plugin.
Dialects = per-dialect eval set + normaliser + confirmation; claim only measured. RAG = stories only.

## Evaluation (never invent numbers; report only measured)
WER on own elderly clips (clean/noisy/code-mixed) • intent + slot accuracy (rules vs classifier vs
Evon) • task success without touching screen • end-of-speech → first-audio latency • BVC A/B •
distress test set (must pass before any public demo) • memory-recall correctness.

## Unknowns — ask the human, don't assume
Prisma streaming support for our target language • credit cost per call • Evon hosting cost and
HF approval • BVC effect on Prisma accuracy • whether LiveKit turn settings can change mid-session •
which embedding model retrieves well in Marathi • Discord: non-Gnani LLM allowed? consenting
relative in demo video?

## Timeline
Oct 13–19 rule-based care mode end-to-end (voice reminder works) • Oct 20–26 scheduler, dashboard,
medicines, Evon, companion, openers, Memory Book, distress • Oct 27–Nov 2 eval, BVC A/B, latency,
deploy, demo; main demo posted ~Nov 1 • Nov 3–8 fixes, write-up, follow-up posts, submit.
60-s demo: problem → voice reminder + live dashboard → recipe taught → Memory Book → "Built on
Gnani AI's Prisma, Evon and Timbre."

## Coding conventions
- Python 3.11+, type hints, Pydantic v2, ruff + pytest. TypeScript strict, no `any`.
- Every tool endpoint: pytest for valid, invalid, ambiguous input. Medicine + distress paths have
  dedicated tests.
- Small PRs; plan mode for anything touching >2 files.

## Commands
- `docker compose up` — run everything locally
- `pytest` inside each service
- `python eval/run_eval.py` — run evaluation suite
