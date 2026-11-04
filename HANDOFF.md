# HANDOFF (2026-11-04, LLM-first understanding + companion context)

## Where we are
Understanding is now LLM-first: one Sarvam call per non-safety turn gets the full sentence, the last turns and a
USER CONTEXT block, and returns strict JSON `{intent, slots, reply, confidence}`. The rule parser is a fallback
(timeout, provider error, invalid JSON, unknown intent, or confidence < 0.4 for an action) and every fallback is
logged with its reason. The safety floor (emergency/distress rules + the second look) still runs first and works with
the LLM and core-api down. Everything is committed locally, nothing is pushed.

## What changed (details in STATUS.md, design in docs/ENGINEERING.md §14)
- `services/reasoning/reasoning_svc/evon.py`: `understand_turn()` (unified prompt, strict JSON, legacy intent names
  still accepted and marked `legacy`, plain prose treated as a chat reply), companion prompt, narrowed sanitizer,
  `max_tokens` default 250, temperature 0.5.
- `services/reasoning/reasoning_svc/turn.py`: LLM-first `handle`; `_understand`, `_user_context`, `_parsed_from_llm`,
  `_chat_reply`; pending/draft/media-choice/check-in/BP state resolved from LLM slots; deterministic state answers
  (yes/no, stop, medicine taken, time/next-up, greeting, hearing check) stay rule-decided; media behaviour preserved.
- `services/reasoning/reasoning_svc/config.py`: 250-token default, temperature 0.5, context limits.
- `services/reasoning/reasoning_svc/parser.py`: a sentence that only mentions "औषध" is no longer a medicine turn.
- `services/reasoning/reasoning_svc/core_client.py`: `checkin_card()` (`GET /users/{id}/checkins/card`) and
  `wellbeing_today()` (`GET /users/{id}/wellbeing/today`) for the context block.
- `services/reasoning/reasoning_svc/main.py`: `TurnOut.action: dict[str, Any]`.
- Tests: `test_llm_policy.py` rewritten to the new contract; `test_llm_config.py`, `test_reply_quality.py`,
  `test_llm_compare.py`, `test_app_commands.py`, `test_media_intents.py` aligned.
- Eval: `eval/companion_eval.jsonl` (50 realistic Marathi utterances), `scripts/eval_companion.py`
  (`--eval` / `--replay N`, `--legacy` for the before measurement, `--tag` names the saved rows).

## Verified (2026-11-04)
- reasoning 894, core-api 244, voice-agent 209, scheduler 8, vitest 114; `tsc --noEmit` and `ruff check .` clean.
- `eval/run_eval.py`: intent 42/42, slots 12/12, distress 5/5, emergency 87/87, false alarms 0/12.
- `scripts/eval_companion.py --eval` (fresh throwaway user per utterance) before vs after:
  46/50 vs 50/50 turns reached a reply (4 requests failed in the old stack, 1 judge failure); relevant 1.47 -> 1.54,
  understood 1.58 -> 1.62, about_her 1.40 -> 1.38, solution 0.91 -> 0.98, natural_marathi 1.73 -> 1.8,
  safe 1.0 -> 0.98; action intent 20/27 -> 26/30; routes 17 LLM / 29 rules -> 49 LLM / 1 rule;
  banned "जमत नाही / आता कसं" lines 3 -> 0. The before run is the previous commit in a worktree with `--legacy`
  (its 80-token configuration).
- `--replay 30` before vs after: 23/30 LLM + 7/30 rules -> 28/30 LLM + 1 rule (1 client timeout, 29 answered);
  0 `finish_reason=length`; 1 sanitizer rejection (medical) after.
- The eval starts the stack in a temp directory with a throwaway SQLite file and forces Sarvam for both the turn and
  the judge, so no repo file, log, database or secret was touched. Each utterance now gets its own user: the dataset
  is 50 independent sentences, and a shared user leaked a pending reminder and an undo window into the next item.

## Known weak spots (real, not hidden)
- Two action questions still get the fixed doctor line instead of a useful answer: "औषधांची गोळी किती घ्यायची?" and
  "माझी गोळी चुकली तर काय करू?" (dose guidance is deliberately forbidden - route them to the family/doctor, do not
  invent a dose).
- A recipe ask ("पुरणपोळी कशी करतात थोडक्यात सांग") sometimes gets the doctor line; it should be an ordinary chat
  answer.
- Severe STT noise ("मोचात घालून", long garbled strings) honestly answers "समजलं नाही" and offers the family. That is
  the intended floor, not a bug, but it is still the loudest pattern in the replay.
- One replay turn hit the script's 30 s client timeout; the reasoning call itself is bounded, but a slow Sarvam turn
  plus the safety second look can exceed the eval client. Not seen from the voice path.
- The judge averages barely move (relevant +0.07, solution +0.07, about_her -0.02, within run-to-run noise at
  temperature 0.5). The measured wins are the turns that completed (46 -> 50), the action intents (20/27 -> 26/30),
  the rule share (29/50 -> 1/50) and the zero banned lines. Quote those, not a "quality score went up".

## Do this first
1. **Root `.env` still has `LLM_MAX_TOKENS=80`.** The code default is 250 but the live stack reads the env line, so
   replies stay short/cut until it is changed (or removed). It was deliberately not edited here. The eval child sets
   the value itself, so the before/after numbers above are unaffected.
2. If you change the companion prompt, re-run `scripts/eval_companion.py --eval --tag <name>` and compare against the
   after numbers above; do not judge by reading one reply.

## Phone test (about 10 minutes)
1. `scripts\dev-up.ps1 -Phone`, open the elder page on the phone, tap to start, let the greeting finish.
2. Talk normally for a minute: a story with "औषध" in it must stay a story; "आज काय करायचंय?" must mention her real
   day; "मला एकटं वाटतंय" must point at a named family member, not a generic line.
3. Ask a reminder ("उद्या सकाळी दहाला ... आठवण करून दे"), confirm it is read back with the right day/time, then ask
   "उद्या काय आहे?" and check the same reminder comes back from SQL.
4. Turn the network off for a moment / stop reasoning and say "मला छातीत दुखतंय": the emergency flow must still run.
