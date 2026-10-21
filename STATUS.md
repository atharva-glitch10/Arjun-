# STATUS (2026-10-21)

## Done
- T1: first commit on `main`, `.gitignore` expanded.
- T2 (file part): `.env.example` lists every variable the code reads, one comment each.

## In progress / blocked
- T2: waiting for "keys rotated" (user rotates Gnani + LiveKit keys), then paste "registered worker" log line.
- T3: approved design, not started. dotenv_values() in agent.py copying only GNANI_*/LIVEKIT_*, fail fast on missing names;
  single scripts/dev-up.ps1; delete both old run-dev.ps1 in the same commit. Waiting for user sign-off before the T3 check.

## Next
- T3 implementation, then T4 after keys are rotated.
