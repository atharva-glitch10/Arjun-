# STATUS (2026-10-21)

## Done
- T1: first commit on `main`, `.gitignore` expanded.
- T2 (file part): `.env.example` lists every variable the code reads, one comment each.

- T3: voice-agent loads GNANI_*/LIVEKIT_* from root .env via dotenv_values (fail-fast on missing names); `scripts/dev-up.ps1`
  starts core-api, reasoning, voice-agent, web; old run-dev.ps1 files removed. Worker registered with rotated keys (2026-10-21).
- T2: keys rotated by user; "registered worker" line confirmed.

## In progress / blocked
- T4: prep done (TTS model/voice from config, per-turn log, scripts/make_token.py). Waiting for user to join the Playground and speak.

- TTS: GNANI_TTS_MODEL=timbre-v2.5 / GNANI_TTS_VOICE=Omkar from config; real plugin synth returned audio (2026-10-21).
- Fix: agent now lets .env override stale inherited GNANI_*/LIVEKIT_* (a pre-rotation shell gave 403 API_KEY_INACTIVE).

## Next
- T4 live voice test.
