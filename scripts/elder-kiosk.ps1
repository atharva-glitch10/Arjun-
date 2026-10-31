# Open the elder screen full-screen on the dedicated elder device, with NO tap needed for sound.
# Browsers block audio until a tap; this Chrome profile is started with autoplay allowed, so Arjun can speak a
# reminder the moment the page opens. Use it ONLY on the elder's own device (it affects this profile only).
# The first run asks once for the microphone; tick "allow" and it is remembered for this profile.
# Usage: scripts\elder-kiosk.ps1 [-Url http://localhost:5173/] [-NoKiosk]
param([string]$Url = "http://localhost:5173/", [switch]$NoKiosk)

$chrome = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { throw "Chrome not found. Install Chrome, or open $Url in Edge and tap the screen once." }

$profile = Join-Path $env:LocalAppData "ArjunElderProfile"   # separate profile: the user's own Chrome is untouched
$args = @("--user-data-dir=$profile", "--autoplay-policy=no-user-gesture-required", "--no-first-run",
          "--disable-session-crashed-bubble", "--disable-infobars")
if (-not $NoKiosk) { $args += "--kiosk" }
$args += $Url
Start-Process -FilePath $chrome -ArgumentList $args
Write-Host "Elder screen opened at $Url (Alt+F4 closes kiosk mode)."
