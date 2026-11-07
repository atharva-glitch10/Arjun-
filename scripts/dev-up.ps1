# Start the local dev stack (no Docker), in order: core-api :8000, reasoning :8001, scheduler, voice-agent, web :5173.
# Reads the ONE root .env. Each service gets its own window and ONLY the variables it needs;
# values are never printed or put on a command line (they travel in the child's environment).
# voice-agent loads its own GNANI_*/LIVEKIT_* from .env (see agent.py), so they are not passed here.
# Usage: scripts\dev-up.ps1 [-Only core-api|reasoning|scheduler|voice-agent|web] [-Phone]
#   -Phone also starts a Cloudflare quick tunnel to :5173, writes its URL to BASE_URL in .env and
#   (re)starts core-api so family-call links use it. Only the BASE_URL line is changed.
#   -Phone needs ARJUN_ACCESS_CODE (6+ characters) in .env: it also restarts web so the tunnel is locked, and prints
#   the phone links WITH the code. Without the code the tunnel would hand the API to anyone, so it is refused.
param(
    [ValidateSet("core-api", "reasoning", "scheduler", "voice-agent", "web")][string]$Only,
    [switch]$Phone
)

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
    CORE_API_URL = "http://127.0.0.1:8000"
    REASONING_URL = "http://127.0.0.1:8001"
}
$local.PYTHONUNBUFFERED = "1"
function Get-Setting([string]$name) { if ($local.ContainsKey($name)) { $local[$name] } else { $dotenv[$name] } }

$tunnelLog = Join-Path $logDir "tunnel.log"
$script:tunnelUrl = ""
$tunnelHelper = Join-Path $PSScriptRoot "tunnel_url.py"

function Get-TunnelUrlFromLog {
    if (-not (Test-Path $tunnelLog)) { return $null }
    $found = & $py $tunnelHelper find $tunnelLog 2>$null
    if ($LASTEXITCODE -eq 0 -and $found) { return ($found | Select-Object -Last 1).Trim() }
    return $null
}

function Get-TunnelProcesses {
    try {
        return @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match 'cloudflared' -and
            $_.CommandLine -match 'tunnel' -and
            $_.CommandLine -match 'localhost:5173' -and
            $_.Name -notmatch '^powershell'
        })
    } catch { return @() }
}

function Test-TunnelUrl([string]$url) {
    if (-not $url) { return $false }
    try {
        $res = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 3
        return ($res.StatusCode -eq 200)
    } catch { return $false }
}

function Stop-Tunnel {
    # Close the "arjun tunnel" window too, not just cloudflared/npx, so a restart is clean.
    try {
        Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
            $_.Name -match '^powershell' -and $_.CommandLine -match 'arjun tunnel'
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch { }
    foreach ($proc in (Get-TunnelProcesses)) {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Stop-WebDev {
    # Used by -Phone: a running web server only reads ARJUN_ACCESS_CODE when it starts, so restart it.
    try {
        Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
            $_.Name -match '^powershell' -and $_.CommandLine -match 'arjun web'
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch { }
    $listeners = @()
    try { $listeners = @(Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction Stop) } catch { }
    foreach ($ownerPid in ($listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerPid" -ErrorAction SilentlyContinue
        if (-not $proc -or $proc.CommandLine -notmatch 'vite') { continue }
        Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
    }
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Test-PortListening 5173)) { return }
        Start-Sleep -Milliseconds 250
    }
}

function Stop-CoreApi {
    # Used by -Phone: a running core-api keeps the old BASE_URL until it is restarted.
    try {
        Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
            $_.Name -match '^powershell' -and $_.CommandLine -match 'arjun core-api'
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch { }

    $listeners = @()
    try { $listeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop) } catch { }
    foreach ($ownerPid in ($listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerPid" -ErrorAction SilentlyContinue
        if (-not $proc -or $proc.CommandLine -notmatch 'core_api\.main:app') { continue }
        Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
    }
    for ($i = 0; $i -lt 20; $i++) {
        $still = @()
        try { $still = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop) } catch { }
        if ($still.Count -eq 0) { return }
        Start-Sleep -Milliseconds 250
    }
}

function Test-PortListening([int]$port) {
    try { return @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop).Count -gt 0 }
    catch { return $false }
}

function Test-ServiceRunning([string]$name) {
    switch ($name) {
        "core-api"  { return (Test-PortListening 8000) }
        "reasoning" { return (Test-PortListening 8001) }
        "web"       { return (Test-PortListening 5173) }
        default {
            try {
                return @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
                    $_.Name -match '^powershell' -and $_.CommandLine -match "arjun $name"
                }).Count -gt 0
            } catch { return $false }
        }
    }
}

function Start-PhoneTunnel {
    $url = Get-TunnelUrlFromLog
    $running = @(Get-TunnelProcesses).Count -gt 0
    if ($running -and $url -and (Test-TunnelUrl $url)) {
        Write-Host "reusing the running tunnel $url"
        return $url
    }
    if ($running) {
        Write-Warning "a tunnel is running but its logged URL is missing or not reachable; restarting it"
        Stop-Tunnel
        Start-Sleep -Milliseconds 500
    }
    if (Test-Path $tunnelLog) { Remove-Item $tunnelLog -Force -ErrorAction SilentlyContinue }

    $webDir = Join-Path $root "web"
    # npm_config_yes avoids the first-run "Ok to proceed?" prompt inside the new window. Add-Content -Encoding
    # utf8 is the same tee the service windows use (Tee-Object would write UTF-16 in Windows PowerShell 5.1).
    $cmd = "`$host.UI.RawUI.WindowTitle='arjun tunnel'; Set-Location '$webDir'; `$env:npm_config_yes='true'; npx cloudflared tunnel --url http://localhost:5173 2>&1 | ForEach-Object { `$s = `$_.ToString(); Add-Content -Path '$tunnelLog' -Value `$s -Encoding utf8; `$s }"
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $cmd
    Write-Host "starting the Cloudflare tunnel (first run may download cloudflared) ..."
    $found = & $py $tunnelHelper wait $tunnelLog --timeout 30 --interval 0.5 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $found) {
        throw "Cloudflare tunnel did not print a trycloudflare.com URL within 30 s. See $tunnelLog"
    }
    return ($found | Select-Object -Last 1).Trim()
}

function Set-EnvBaseUrl([string]$url) {
    & $py $tunnelHelper set-base-url $envFile $url
    if ($LASTEXITCODE -ne 0) { throw "could not write BASE_URL to $envFile" }
    $dotenv["BASE_URL"] = $url
}

$services = [ordered]@{
    "core-api"    = @{ Dir = "services\core-api"; Cmd = "& '$py' -m uvicorn core_api.main:app --port 8000"
                       Vars = "DATABASE_URL", "CORE_API_KEY", "ARJUN_TZ", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "ARJUN_AGENT_NAME",
                       "CORE_RATE_LIMIT", "CORE_RATE_PER_S", "CORE_RATE_BURST", "UNDO_TTL_S", "FEED_RECHECK_S", "YOUTUBE_API_KEY",
                       "YOUTUBE_MAX_SEARCHES_PER_DAY", "TELEGRAM_ENABLED", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
                       "BASE_URL", "JOIN_SECRET", "ARJUN_CHECKINS_ENABLED", "ARJUN_CHECKIN_MAX_PER_DAY", "ARJUN_CHECKIN_MIN_GAP_MIN", "ARJUN_CHECKIN_DEMO",
                       "BRIEFING_TIME", "BRIEFING_VOICE_URL" }
    "reasoning"   = @{ Dir = "services\reasoning"; Cmd = "& '$py' -m uvicorn reasoning_svc.main:app --port 8001"
                       Vars = "CORE_API_URL", "CORE_API_KEY", "ARJUN_TZ", "EVON_BASE_URL", "EVON_MODEL", "EVON_API_KEY", "EVON_SEND_TEMPLATE_KWARGS",
                       "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "LLM_PROVIDER_NAME", "LLM_SEND_TEMPLATE_KWARGS",
                       "LLM_TIMEOUT_S", "LLM_MAX_TOKENS", "LLM_HISTORY_EXCHANGES", "ARJUN_SESSION_EXCHANGES", "ARJUN_SESSION_IDLE_MIN", "ARJUN_FACTS_IN_CONTEXT",
                       "SARVAM_API_KEY", "SARVAM_MODEL", "SARVAM_BASE_URL", "LLM_REASONING", "LLM_MAX_CONCURRENT", "LLM_PER_MINUTE",
                       "ARJUN_ASK_BEFORE_ACTING", "UNDO_WINDOW_S", "TURN_RATE_PER_S", "TURN_RATE_BURST", "CONVERSATION_IDLE_S" }
    "scheduler"   = @{ Dir = "services\scheduler"; Cmd = "& '$py' scheduler.py"
                       # queues reminders/medicines and asks core-api to send due briefings; openers use check-in opt-in.
                       Vars = "CORE_API_URL", "CORE_API_KEY", "REASONING_URL", "ARJUN_TZ", "SCHEDULER_INTERVAL_SECONDS",
                              "OPENER_USER_IDS" }
    "voice-agent" = @{ Dir = "services\voice-agent"; Cmd = "& '$py' agent.py dev"
                       Vars = "CORE_API_KEY", "REASONING_URL", "REASONING_TIMEOUT_S", "ARJUN_USER_ID", "ARJUN_TZ", "ARJUN_VOICE_PROVIDER",
                       "ARJUN_SARVAM_SPEAKER", "SARVAM_API_KEY" }
    "web"         = @{ Dir = "web"; Cmd = "npm run dev"; Vars = "CORE_API_KEY", "CORE_API_URL", "ARJUN_ACCESS_CODE" }  # the Vite proxy injects the key; the browser never talks to reasoning
}

function Wait-Health([string]$url, [string]$label) {
    for ($i = 0; $i -lt 30; $i++) {
        try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null; Write-Host "$label is up"; return }
        catch { Start-Sleep -Seconds 1 }
    }
    Write-Warning "$label did not answer $url within 30 s; continuing"
}

if ($Phone) {
    $accessCode = (Get-Setting "ARJUN_ACCESS_CODE")
    if (-not $accessCode -or $accessCode.Length -lt 6) {
        throw "ARJUN_ACCESS_CODE is missing or shorter than 6 characters. Add it to the root .env (see .env.example), then run again. A tunnel without it would give the API to anyone with the URL."
    }
    if ($accessCode -notmatch '^[A-Za-z0-9_-]+$') {
        throw "ARJUN_ACCESS_CODE may contain only letters, digits, '-' and '_' (it goes into a link)."
    }
    $script:tunnelUrl = Start-PhoneTunnel
    Set-EnvBaseUrl $script:tunnelUrl
    Write-Host "BASE_URL set to $script:tunnelUrl (only that .env line changed)"
}

foreach ($name in $services.Keys) {
    if ($Only -and $Only -ne $name) { continue }
    if ($Phone -and $name -eq "web" -and (Test-ServiceRunning $name)) { Write-Host "restarting web so it applies the access lock"; Stop-WebDev }
    if ($Phone -and $name -notin @("core-api", "web") -and (Test-ServiceRunning $name)) {
        Write-Host "$name is already running; leaving it alone"
        continue
    }
    if ($Phone -and $name -eq "core-api") { Stop-CoreApi }  # so it reads the new BASE_URL
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
Write-Host "core-api http://127.0.0.1:8000/docs | reasoning http://127.0.0.1:8001/docs | web http://localhost:5173"

if ($Phone) {
    if ($Only -and $Only -ne "core-api") {
        Write-Warning "-Only ${Only}: core-api was not restarted, so it may still have the old BASE_URL. Run -Only core-api to apply it."
    }
    if ($script:tunnelUrl) {
        $elder = "$($script:tunnelUrl)/?user=1&k=$accessCode"
        $family = "$($script:tunnelUrl)/?view=family&user=1&k=$accessCode"
        Write-Host ""
        Write-Host "================= PHONE URLS (HTTPS) =================" -ForegroundColor Green
        Write-Host ""
        Write-Host "  ELDER   $elder" -ForegroundColor Green
        Write-Host "  FAMILY  $family" -ForegroundColor Green
        Write-Host ""
        Write-Host "  The links carry the access code: share them only with the people who should see this."
        Write-Host "  A phone opens a link once; the code is then swapped for a 12 h cookie and removed from the address."
        Write-Host "  A link without the code, or with a wrong one, shows 'हा दुवा चालत नाही'. Telegram join links need no code."
        Write-Host "  Demo data only."
        Write-Host "======================================================" -ForegroundColor Green
        Write-Host ""
    }
}
