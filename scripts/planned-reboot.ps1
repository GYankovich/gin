# Forced reboot used by the daily task and by host-watch.
# Logs the reason, then gives Windows 90 seconds to flush disks.
#
#   powershell -File scripts/planned-reboot.ps1 -Reason "daily"
#   powershell -File scripts/planned-reboot.ps1 -Reason "rdp down" -DryRun

param(
    [string]$Reason = "scheduled",
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $Root "logs\boot"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "reboot.log"
$Marker = Join-Path $LogDir "last-forced-reboot.txt"

$line = "{0}  reason={1} dryRun={2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Reason, [bool]$DryRun
Add-Content -Path $LogFile -Value $line -Encoding UTF8
Write-Host $line

if ($DryRun) {
    Write-Host "dry-run: would run shutdown /r /f /t 90"
    exit 0
}

Set-Content -Path $Marker -Value $line -Encoding ASCII
& shutdown.exe /r /f /t 90 /c "GIN reboot: $Reason"
exit $LASTEXITCODE
