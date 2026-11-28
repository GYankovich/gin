# After logon, WebStorm itself starts the project.
# Startup tasks in .idea/startup.xml run:
#   GIN backend  -> python backend/run.py all --kill-ports
#   nginx:start  -> npm run nginx:start
#
# The scheduled task GIN-WebStorm is webstorm64.exe, not this script.
# A short script must not parent the IDE: Task Scheduler would kill it on exit.
#
#   powershell -File scripts/boot-gin.ps1 -DryRun
#   powershell -File scripts/boot-gin.ps1

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $Root "logs\boot"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "boot.log"

function Write-BootLog([string]$Message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

Write-BootLog "boot-gin (dryRun=$DryRun): start WebStorm, IDE runs backend and nginx:start"

if ($DryRun) {
    Write-BootLog "dry-run: would Start-ScheduledTask GIN-WebStorm"
    exit 0
}

Start-ScheduledTask -TaskName "GIN-WebStorm"
Write-BootLog "GIN-WebStorm started"
exit 0
