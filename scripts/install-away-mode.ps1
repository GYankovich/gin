# Unattended week: reboot every day at 05:10.
# On logon, WebStorm opens this project and its startup tasks run
# the backend and npm run nginx:start.
#
# Run once from an elevated PowerShell (this script asks for UAC itself):
#   powershell -ExecutionPolicy Bypass -File scripts/install-away-mode.ps1
#
# Remove the tasks when you are back:
#   powershell -ExecutionPolicy Bypass -File scripts/install-away-mode.ps1 -Uninstall

param(
    [switch]$Uninstall,
    [string]$RebootAt = "05:10"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $Root "logs\boot"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$ResultFile = Join-Path $LogDir "install-result.txt"

function Write-Result([string]$Message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $ResultFile -Value $line -Encoding UTF8
    Write-Host $line
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).
    IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", $PSCommandPath,
        "-RebootAt", $RebootAt
    )
    if ($Uninstall) { $args += "-Uninstall" }
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $args | Out-Null
    Write-Host "UAC prompt opened. Result will be written to $ResultFile"
    exit 0
}

Set-Content -Path $ResultFile -Value ("{0}  install start uninstall={1} rebootAt={2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), [bool]$Uninstall, $RebootAt) -Encoding UTF8
trap {
    Write-Result ("ERROR: " + $_)
    exit 1
}

$taskNames = @("GIN-Boot", "GIN-Nginx", "GIN-WebStorm", "GIN-DailyReboot", "GIN-HostWatch")
foreach ($name in $taskNames) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Result "removed task $name (if it existed)"
}

if ($Uninstall) {
    Write-Result "uninstall done"
    exit 0
}

# RDP must be up after reboot without a person at the console.
# Do not restart the service here: that would cut the current session.
Set-Service -Name TermService -StartupType Automatic
Write-Result "TermService startup=Automatic (not restarted)"

powercfg /change standby-timeout-ac 0 | Out-Null
powercfg /change hibernate-timeout-ac 0 | Out-Null
powercfg /change disk-timeout-ac 0 | Out-Null
powercfg /SETACVALUEINDEX SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0 | Out-Null
powercfg /SETACTIVE SCHEME_CURRENT | Out-Null
Write-Result "power: no sleep, no hibernate, no disk timeout, no usb selective suspend on AC"

try {
    $physical = @(Get-NetAdapter -Physical | Where-Object { $_.Status -eq "Up" })
    foreach ($adapter in $physical) {
        Disable-NetAdapterPowerManagement -Name $adapter.Name -ErrorAction SilentlyContinue
        Write-Result "nic power management off: $($adapter.InterfaceDescription)"
    }
    if ($physical.Count -eq 0) {
        Write-Result "no physical adapter is Up; nic power management unchanged"
    }
} catch {
    Write-Result "nic power management skipped: $_"
}

function New-GinSettings([int]$RestartCount = 0) {
    $params = @{
        AllowStartIfOnBatteries = $true
        DontStopIfGoingOnBatteries = $true
        DontStopOnIdleEnd = $true
        MultipleInstances = "IgnoreNew"
        ExecutionTimeLimit = (New-TimeSpan -Seconds 0)
        StartWhenAvailable = $false
    }
    if ($RestartCount -gt 0) {
        $params.RestartCount = $RestartCount
        $params.RestartInterval = (New-TimeSpan -Minutes 2)
    }
    $settings = New-ScheduledTaskSettingsSet @params
    $settings.AllowDemandStart = $true
    $settings.ExecutionTimeLimit = "PT0S"
    return $settings
}

$system = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

$webstorm = "C:\Program Files\JetBrains\WebStorm 2025.2\bin\webstorm64.exe"
if (-not (Test-Path $webstorm)) { throw "webstorm64.exe not found: $webstorm" }
$user = $env:USERNAME
$userPrincipal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$ideAction = New-ScheduledTaskAction -Execute $webstorm -Argument $Root -WorkingDirectory $Root
$ideTrigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$ideTrigger.Delay = "PT45S"
Register-ScheduledTask -TaskName "GIN-WebStorm" -Action $ideAction -Trigger $ideTrigger -Principal $userPrincipal -Settings (New-GinSettings 0) -Force | Out-Null
Write-Result "registered GIN-WebStorm at logon of $user +45s"

$rebootAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Root\scripts\planned-reboot.ps1`" -Reason daily" `
    -WorkingDirectory $Root
$rebootTrigger = New-ScheduledTaskTrigger -Daily -At $RebootAt
Register-ScheduledTask -TaskName "GIN-DailyReboot" -Action $rebootAction -Trigger $rebootTrigger -Principal $system -Settings (New-GinSettings 0) -Force | Out-Null
Write-Result "registered GIN-DailyReboot daily at $RebootAt"

# Minute schedule survives reboot. A one-shot trigger with a repetition often does not.
$watchTr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Root\scripts\host-watch.ps1"
& schtasks.exe /Create /F /TN "GIN-HostWatch" /SC MINUTE /MO 20 /RU "SYSTEM" /RL HIGHEST /TR $watchTr
if ($LASTEXITCODE -ne 0) { throw "schtasks GIN-HostWatch failed: $LASTEXITCODE" }
$watchTask = Get-ScheduledTask -TaskName "GIN-HostWatch"
$watchTask.Settings.ExecutionTimeLimit = "PT0S"
$watchTask.Settings.DisallowStartIfOnBatteries = $false
$watchTask.Settings.StopIfGoingOnBatteries = $false
$watchTask.Settings.StartWhenAvailable = $false
$watchTask.Settings.MultipleInstances = "IgnoreNew"
Set-ScheduledTask -InputObject $watchTask | Out-Null
Write-Result "registered GIN-HostWatch every 20 min"

$auto = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -ErrorAction SilentlyContinue
Write-Result ("autologon={0} user={1}" -f $auto.AutoAdminLogon, $auto.DefaultUserName)

foreach ($name in @("GIN-WebStorm", "GIN-DailyReboot", "GIN-HostWatch")) {
    $task = Get-ScheduledTask -TaskName $name
    $info = Get-ScheduledTaskInfo -TaskName $name
    $action = $task.Actions | Select-Object -First 1
    Write-Result ("task {0} state={1} limit={2} next={3} exec={4}" -f $name, $task.State, $task.Settings.ExecutionTimeLimit, $info.NextRunTime, $action.Execute)
}

Write-Result "install done. First forced reboot is the next $RebootAt. Cancel a pending one with: shutdown /a"
exit 0
