# STATUS (2026-10-21)

## Done
- T1: first commit on `main`, `.gitignore` expanded.
- T2 (file part): `.env.example` lists every variable the code reads, one comment each.

- T3: voice-agent loads GNANI_*/LIVEKIT_* from root .env via dotenv_values (fail-fast on missing names); `scripts/dev-up.ps1`
  starts core-api, reasoning, voice-agent, web; old run-dev.ps1 files removed. Worker registered with rotated keys (2026-10-21).
- T2: keys rotated by user; "registered worker" line confirmed.

## In progress / blocked
- T4: waiting for user (LiveKit token + Playground join, spoken test).

## Next
- T4 live voice test.
