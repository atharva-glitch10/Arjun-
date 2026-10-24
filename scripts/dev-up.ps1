# Start the local dev stack (no Docker), in order: core-api :8000, reasoning :8001, voice-agent, web :5173.
# Reads the ONE root .env. Each service gets its own window and ONLY the variables it needs;
# values are never printed or put on a command line (they travel in the child's environment).
# voice-agent loads its own GNANI_*/LIVEKIT_* from .env (see agent.py), so they are not passed here.
# Usage: scripts\dev-up.ps1 [-Only core-api|reasoning|voice-agent|web]
param([ValidateSet("core-api", "reasoning", "voice-agent", "web")][string]$Only)

$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $root ".venv\Scripts\python.exe"
$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) { throw "Missing $envFile - copy .env.example to .env first." }

$logDir = Join-Path $root "logs"   # per-service output, git-ignored
New-Item -ItemType Directory -Force $logDir | Out-Null

$dotenv = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$' -and $line -notmatch '^\s*#') {
        $dotenv[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
    }
}

# Local-run overrides: .env may point at compose-only hosts (postgres, core-api, reasoning).
$local = @{
    DATABASE_URL = "sqlite:///./arjun.db"
    CORE_API_URL = "http://localhost:8000"
    REASONING_URL = "http://localhost:8001"
}
$local.PYTHONUNBUFFERED = "1"
function Get-Setting([string]$name) { if ($local.ContainsKey($name)) { $local[$name] } else { $dotenv[$name] } }

$services = [ordered]@{
    "core-api"    = @{ Dir = "services\core-api"; Cmd = "& '$py' -m uvicorn core_api.main:app --port 8000"
                       Vars = "DATABASE_URL", "CORE_API_KEY", "ARJUN_TZ" }
    "reasoning"   = @{ Dir = "services\reasoning"; Cmd = "& '$py' -m uvicorn reasoning_svc.main:app --port 8001"
                       Vars = "CORE_API_URL", "CORE_API_KEY", "ARJUN_TZ", "EVON_BASE_URL", "EVON_MODEL", "EVON_API_KEY", "EVON_SEND_TEMPLATE_KWARGS" }
    "voice-agent" = @{ Dir = "services\voice-agent"; Cmd = "& '$py' agent.py dev"
                       Vars = "REASONING_URL", "REASONING_TIMEOUT_S", "ARJUN_USER_ID", "ARJUN_TZ" }
    "web"         = @{ Dir = "web"; Cmd = "npm run dev"; Vars = @() }
}

function Wait-Health([string]$url, [string]$label) {
    for ($i = 0; $i -lt 30; $i++) {
        try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null; Write-Host "$label is up"; return }
        catch { Start-Sleep -Seconds 1 }
    }
    Write-Warning "$label did not answer $url within 30 s; continuing"
}

foreach ($name in $services.Keys) {
    if ($Only -and $Only -ne $name) { continue }
    $svc = $services[$name]
    $saved = @{}
    $svc.Vars += "PYTHONUNBUFFERED"   # piped python otherwise buffers its log lines
    foreach ($v in $svc.Vars) {
        $val = Get-Setting $v
        if ($val) { $saved[$v] = [Environment]::GetEnvironmentVariable($v, "Process"); [Environment]::SetEnvironmentVariable($v, $val, "Process") }
    }
    $dir = Join-Path $root $svc.Dir
    $log = Join-Path $logDir "$name.log"
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", "`$host.UI.RawUI.WindowTitle='arjun $name'; Set-Location '$dir'; $($svc.Cmd) 2>&1 | ForEach-Object { `$s = `$_.ToString(); Add-Content -Path '$log' -Value `$s -Encoding utf8; `$s }"
    foreach ($v in $saved.Keys) { [Environment]::SetEnvironmentVariable($v, $saved[$v], "Process") }
    Write-Host "started $name"
    if (-not $Only) {
        if ($name -eq "core-api") { Wait-Health "http://127.0.0.1:8000/health" "core-api" }
        if ($name -eq "reasoning") { Wait-Health "http://127.0.0.1:8001/health" "reasoning" }
    }
}
Write-Host "core-api http://localhost:8000/docs | reasoning http://localhost:8001/docs | web http://localhost:5173"
