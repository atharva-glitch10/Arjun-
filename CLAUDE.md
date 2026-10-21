# CLAUDE.md - Arjun project spec and hard boundaries

Arjun is a voice companion that helps elderly Indians (Marathi / code-mixed / Hindi / English) manage
their day and share life stories by talking. Two halves: a **reliable assistant** (reminders, schedule,
help) and a **warm listener** (stories, interests, Memory Book).
Principle: **Arjun is a bridge to people, not a replacement for them.**

Built for the Gnani AI contest. Target award: Main Character (regional language); backup: Real Deal.
Submit by Nov 8; main public demo posted by ~Nov 1.

## Hard boundaries (never violate, never "improve" away)
1. **The LLM never touches the database.** Evon only suggests; core-api validates and acts.
   Flow: reasoning proposes -> core-api stores a *pending* action -> only a spoken yes executes it.
2. **Reminders, appointments, contacts come from SQL only.** RAG is for past stories only.
3. **Never guess.** Ambiguous AM/PM, missing date, or "after the meal" without which meal -> ask.
4. **Arjun is an AI.** Say so whenever asked. Never claim to be human, to have feelings or family.
5. **No medical advice**, diagnosis or medicine decisions. Only read back reminders the caregiver set.
6. **Distress check runs first on every turn** and overrides everything: stop the story, respond
   gently, offer a family call, mention Elderline 14567 (8 AM-8 PM), alert caregiver only per consent.
   Distress test set must pass before any public demo.
7. **No engagement tricks**: no streaks, no "I missed you", nothing discouraging human contact.
8. **Companion never recites recipes/facts from model memory.** It asks the user to teach it.
   At most one opener per day window; "nako" means no more that day.
9. **Stories are private by default**; saved only after a yes, shared only after a second yes;
   "he visar" deletes. No raw audio stored. Demo uses synthetic data only.
10. **Secrets**: `GNANI_API_KEY` and LiveKit keys live only in voice-agent's `.env`. Never in React
    code, never in Git, never logged.
11. **Never invent numbers.** Report only what was measured (WER, latency, accuracy).

## Models (Gnani)
| Model | Role | Access |
|---|---|---|
| Prisma | STT, ears (streaming, code-mixed) | Gnani API via LiveKit Gnani plugin (credits) |
| Timbre | TTS, Arjun's male voice | Gnani API via LiveKit Gnani plugin (credits) |
| Evon v3.3 | LLM: messy phrasing, companion talk, summaries | Self-hosted vLLM / Friendli (not covered by credits) |

Layered brain so the app works with the GPU off: rules + Marathi time grammar -> (optional small
classifier) -> Evon. Care mode and distress: temperature 0. Companion: one fixed tested value
(Gnani suggests 0.6; not yet chosen by our testing). Evon thinking off in the live path.

## Architecture
```
Elder device (React, one big button) -> LiveKit room -> voice-agent (Python worker)
  BVC noise filter -> Prisma STT -> reasoning /turn (distress -> router -> rules -> Evon)
  -> core-api (FastAPI, Postgres) -> reply text -> Timbre TTS -> speaker
scheduler: due reminders, briefing, openers, alerts.  Dashboard: React + TS -> core-api.
```
Services in this repo: `services/core-api`, `services/reasoning`, `services/scheduler`,
`services/voice-agent`, `web/`, `shared/schemas`, `eval/`. Stack: Python/FastAPI, React+TS,
PostgreSQL (+pgvector planned), MongoDB for logs only, S3 for one bucket only.

## Scope
MVP: voice reminders, "aaj kay aahe", mark done, family-call reminders, help request, morning
briefing, story listening, interest openers, Memory Book, safety, caregiver dashboard.
Not in MVP: real telephony, news feeds, rescheduling, multi-elder accounts, SMS/WhatsApp,
Evon fine-tuning, more languages.

## Open questions (unresolved; do not assume answers)
1. Does Prisma support Marathi in *streaming*? If not, push-to-talk.
2. Prisma accuracy on elderly speakers? If poor: mandatory confirmation, short phrases.
3. Credit cost per call.
4. Evon hosting cost; HF access approval time.
5. Is a non-Gnani LLM backup allowed? Can a consenting relative appear in the demo video?
6. Does BVC noise cancellation help or hurt Prisma (A/B)?
7. Can LiveKit turn-detection change mid-session? Endpointing 0.7s/1.2s in `bridge.py` are placeholders.

## Working rules for Claude
- Tests: `pytest` inside `services/core-api` and `services/reasoning`; `ruff check .` at root;
  `python eval/run_eval.py`. Run them after changes.
- Don't claim something works unless it was run. Mark unverified code as unverified.
- Keep care-mode replies as fixed templates; don't route them through a free-form LLM.
- Update README "Known limitations" when behaviour or verification status changes.
