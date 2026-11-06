# Arjun MCP server

Lets an outside AI (Claude Code, Claude desktop, OpenCode, Antigravity…) check and use Arjun. stdio, Python.

## Install
```powershell
cd D:\Arjun
.\.venv\Scripts\pip install -r tools\arjun_mcp\requirements.txt
```

## Register
Claude Code: `claude mcp add arjun -- D:\Arjun\.venv\Scripts\python D:\Arjun\tools\arjun_mcp\server.py`

Claude desktop / OpenCode / other MCP clients (JSON config):
```json
{"mcpServers": {"arjun": {"command": "D:\\Arjun\\.venv\\Scripts\\python.exe",
                          "args": ["D:\\Arjun\\tools\\arjun_mcp\\server.py"]}}}
```
(Use your own repo path.) Arjun must be running (`scripts\dev-up.ps1`).

## Tools
| Tool | What it does |
|---|---|
| arjun_health | core-api / reasoning / web up?, phone link, voice provider, Telegram, access lock |
| arjun_logs(service, tail, grep) | newest log of a service, redacted |
| arjun_try_turn(text, user_id?, confirm?) | one sentence through Arjun; default = separate "MCP Test" user |
| arjun_run_tests(suite) | run a test suite, last lines |
| arjun_today / arjun_feed / arjun_medicines / arjun_reminders_today (user_id) | what the family dashboard shows |
| arjun_add_reminder(user_id, sentence) | write: only with `ARJUN_MCP_WRITE=1` in `.env` |

## Safety
- Every output is redacted (keys, tokens, access code, phone numbers → last 4 digits).
- Family tools never return transcripts (summary, mood, seriousness only).
- A real user is only touched by `try_turn` with `confirm=True`; write tools are off unless `ARJUN_MCP_WRITE=1`.

## Example prompts
- "Use arjun_health and tell me why the phone link isn't working."
- "Use arjun_try_turn with 'मला हार्ट अटॅक येतोय' — is it handled as an emergency?"
- "Use arjun_logs voice-agent grep error and explain the last failure."
- "Use arjun_today for user 1: how is she today?"
- "Run arjun_run_tests reasoning and fix any failure."
