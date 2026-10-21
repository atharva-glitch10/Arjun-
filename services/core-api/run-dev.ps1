# Local dev server for core-api: SQLite, no Docker. Run from anywhere.
# Overrides DATABASE_URL because .env points at the compose-only host 'postgres'.
param([int]$Port = 8000)

Set-Location $PSScriptRoot
$env:DATABASE_URL = "sqlite:///./arjun.db"
$env:CORE_API_KEY = "dev-change-me"
& "$PSScriptRoot\..\..\.venv\Scripts\python.exe" -m uvicorn core_api.main:app --port $Port
