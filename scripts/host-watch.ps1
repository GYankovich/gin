# Health check for an unattended week.
# Reboots only when RDP is actually dead, or when half-closed TCP sockets
# have piled up far past the level that already makes the machine sick.
# If the site is down but RDP is fine, restarts the GIN scheduled tasks
# instead of rebooting.
#
#   powershell -File scripts/host-watch.ps1 -DryRun

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $Root "logs\boot"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "watch.log"

function Write-WatchLog([string]$Message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Test-Listening([int]$Port) {
    $pattern = ":$Port\s+\S+\s+LISTENING"
    return [bool](netstat -ano | Select-String -Pattern $pattern)
}

function Get-StateCount([string]$State) {
    return @(netstat -ano | Select-String -Pattern "\s$State\s").Count
}

function Request-Reboot([string]$Reason) {
    $capFile = Join-Path $LogDir ("reboot-count-{0:yyyy-MM-dd}.txt" -f (Get-Date))
    $count = 0
    if (Test-Path $capFile) {
        $parsed = 0
        [void][int]::TryParse((Get-Content $capFile -Raw).Trim(), [ref]$parsed)
        $count = $parsed
    }
    if ($count -ge 4) {
        Write-WatchLog "reboot skipped, daily cap reached ($count): $Reason"
        return
    }

    $marker = Join-Path $LogDir "last-forced-reboot.txt"
    if (Test-Path $marker) {
        $age = (Get-Date) - (Get-Item $marker).LastWriteTime
        if ($age.TotalMinutes -lt 45) {
            Write-WatchLog "reboot skipped, cooldown $([int]$age.TotalMinutes)m: $Reason"
            return
        }
    }

    $count += 1
    if (-not $DryRun) {
        Set-Content -Path $capFile -Value $count -Encoding ASCII
    }
    Write-WatchLog "reboot requested (#$count): $Reason"
    $reboot = Join-Path $PSScriptRoot "planned-reboot.ps1"
    if ($DryRun) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $reboot -Reason $Reason -DryRun
    } else {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $reboot -Reason $Reason
    }
}

function Restart-GinTask([string]$Name) {
    Write-WatchLog "restarting scheduled task $Name"
    if ($DryRun) { return }
    Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Start-ScheduledTask -TaskName $Name
}

if ((Get-Item $LogFile -ErrorAction SilentlyContinue).Length -gt 2MB) {
    Move-Item -Force $LogFile (Join-Path $LogDir "watch.prev.log")
}

$uptime = (Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
$finWait2 = Get-StateCount "FIN_WAIT_2"
$closeWait = Get-StateCount "CLOSE_WAIT"
$rdpListen = Test-Listening 3389
$apiListen = Test-Listening 8000
$tlsListen = Test-Listening 443
$term = (Get-Service -Name TermService -ErrorAction SilentlyContinue).Status

Write-WatchLog ("uptime={0:n0}m rdp={1} term={2} api={3} tls={4} fin_wait_2={5} close_wait={6}" -f `
    $uptime.TotalMinutes, $rdpListen, $term, $apiListen, $tlsListen, $finWait2, $closeWait)

if ($uptime.TotalMinutes -lt 8) {
    Write-WatchLog "boot window, no action"
    exit 0
}

if ($term -ne "Running") {
    Write-WatchLog "TermService is $term, trying to start"
    if (-not $DryRun) {
        Start-Service -Name TermService -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 5
    }
    $term = (Get-Service -Name TermService -ErrorAction SilentlyContinue).Status
    $rdpListen = Test-Listening 3389
    if ($term -ne "Running" -or -not $rdpListen) {
        Request-Reboot "rdp down (service=$term listen=$rdpListen)"
        exit 0
    }
}

if (-not $rdpListen) {
    Request-Reboot "rdp port 3389 not listening"
    exit 0
}

# Current steady leak is a few hundred. Reboot only on a real pile-up.
if ($finWait2 -ge 2500 -or $closeWait -ge 1500) {
    Request-Reboot "tcp wedge fin_wait_2=$finWait2 close_wait=$closeWait"
    exit 0
}

if (-not $tlsListen) {
    Write-WatchLog "nginx is not listening on :443"
    if (-not $DryRun) {
        Get-Process nginx -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Restart-GinTask "GIN-Nginx"
}

if (-not $apiListen) {
    Restart-GinTask "GIN-Boot"
}

exit 0
