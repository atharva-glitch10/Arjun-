# Local dev stack without Docker: core-api :8000 (SQLite), reasoning :8001, web :5173.
# Each service gets its own window. .env points at compose-only hosts ('postgres', 'core-api'),
# so every URL is overridden here. Scheduler and voice-agent are not started (see README).
param([string]$Key = "dev-change-me")

$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

$common = "`$env:CORE_API_KEY='$Key'; `$env:CORE_API_URL='http://localhost:8000'; `$env:REASONING_URL='http://localhost:8001'; `$env:DATABASE_URL='sqlite:///./arjun.db'; "

$services = @(
    @{ Dir = "services\core-api"; Cmd = "& '$py' -m uvicorn core_api.main:app --port 8000" },
    @{ Dir = "services\reasoning"; Cmd = "& '$py' -m uvicorn reasoning_svc.main:app --port 8001" },
    @{ Dir = "web"; Cmd = "npm run dev" }
)

foreach ($s in $services) {
    $dir = Join-Path $root $s.Dir
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", "Set-Location '$dir'; $common$($s.Cmd)"
}

Write-Host "core-api http://localhost:8000/docs | reasoning http://localhost:8001/docs | web http://localhost:5173"
