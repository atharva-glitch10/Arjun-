# Arjun runbook (Windows laptop)

## Start
```powershell
cd "<your Arjun folder>"
git pull
powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1          # laptop only
powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 -Phone   # + Cloudflare tunnel, prints phone links with &k=
```
Five windows open: core-api (:8000), reasoning (:8001), scheduler, voice-agent, web (:5173). Keep them open; closing
a window stops that service. Every new PowerShell window starts in `C:\WINDOWS\system32`: `cd` to the folder first.

| Screen | Laptop URL |
|---|---|
| Elder | http://localhost:5173 (tap-to-talk test mode: `?handsfree=0`) |
| Family dashboard | http://localhost:5173/?view=family |

Phone or tunnel links must be the freshly printed ones with `&k=...`; the tunnel address changes on every start.
"हा दुवा चालत नाही" = old/wrong link or an elder link used for the family view.

## Stop
Close the five windows.

## First live test (one tab only)
1. Close every Arjun tab (laptop and phone). Two tabs = two sessions fighting for the mic.
2. Open the elder URL, tap सुरू करा, allow the microphone. If a medicine reminder shows, tap a button.
3. Tap बोला, say "नमस्कार अर्जुन", wait 10 s.
4. `Get-Content logs\voice-agent.app.log -Tail 60` and read the `voice:` lines.

## Reading the `voice:` log lines (ARJUN_DEBUG_VOICE=1, the default; never contains the words)
| You see | Meaning | Try |
|---|---|---|
| no `user listening -> speaking` | Arjun never detected speech | Chrome mic icon: right microphone, not muted; one tab only |
| `speaking` but warning "Prisma returned no words" | Speech-to-text returned nothing | New/valid `GNANI_API_KEY`; set `GNANI_STT_IMPL=v3` in `.env` (auto language) and restart |
| `stt final: N chars` but no `turn -> reasoning` | Words ignored (video playing / family in room / held fragment) | Speak a full sentence; stop the video |
| `turn -> reasoning` but no `turn answered` | reasoning down or slow | reasoning window for red lines; `http://127.0.0.1:8001/health` |
| `reply voice: ...` but nothing heard | TTS or speaker problem | `error detail:` line; laptop volume; tap the page once (browsers block audio until a tap) |
| `cloned voice synthesis failed (...)` | familiar voice failed, Arjun spoke in its own voice | the bracket says why |

`arjun-diagnose.ps1` (shared in chat) collects health, `.env` names (no values) and all logs into `diag.txt`, keys removed.

## Voice cloning setup
`.env`: `VOICE_CLONE_KEY=<Fernet key>` (make one: `.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
Never change it later (saved voices stop working) and never share it. Dashboard: Family & memories, A familiar voice.

## Checks before a demo
`pytest` in services/core-api, reasoning, voice-agent, scheduler; `ruff check .`; in web `npx tsc --noEmit` and
`npx vitest run`; `python eval/run_eval.py`.
