# Unattended week: boot GIN without a login, reboot every day at 05:10,
# and reboot sooner if RDP or the TCP stack is dead.
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

$taskNames = @("GIN-Boot", "GIN-Nginx", "GIN-DailyReboot", "GIN-HostWatch")
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

function New-GinSettings {
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -DontStopOnIdleEnd `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 2) `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
        -StartWhenAvailable:$false
    $settings.AllowDemandStart = $true
    $settings.ExecutionTimeLimit = "PT0S"
    return $settings
}

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

$bootAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Root\scripts\boot-gin.ps1`"" `
    -WorkingDirectory $Root
$bootTrigger = New-ScheduledTaskTrigger -AtStartup
$bootTrigger.Delay = "PT2M"
Register-ScheduledTask -TaskName "GIN-Boot" -Action $bootAction -Trigger $bootTrigger -Principal $principal -Settings (New-GinSettings) -Force | Out-Null
Write-Result "registered GIN-Boot at startup +2min"

$nginxExe = Join-Path $Root "nginx\nginx.exe"
$nginxDir = Join-Path $Root "nginx"
$nginxAction = New-ScheduledTaskAction -Execute $nginxExe -WorkingDirectory $nginxDir
$nginxTrigger = New-ScheduledTaskTrigger -AtStartup
$nginxTrigger.Delay = "PT1M"
Register-ScheduledTask -TaskName "GIN-Nginx" -Action $nginxAction -Trigger $nginxTrigger -Principal $principal -Settings (New-GinSettings) -Force | Out-Null
Write-Result "registered GIN-Nginx at startup +1min"

$rebootAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Root\scripts\planned-reboot.ps1`" -Reason daily" `
    -WorkingDirectory $Root
$rebootTrigger = New-ScheduledTaskTrigger -Daily -At $RebootAt
Register-ScheduledTask -TaskName "GIN-DailyReboot" -Action $rebootAction -Trigger $rebootTrigger -Principal $principal -Settings (New-GinSettings) -Force | Out-Null
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

foreach ($name in $taskNames) {
    $task = Get-ScheduledTask -TaskName $name
    $info = Get-ScheduledTaskInfo -TaskName $name
    Write-Result ("task {0} state={1} limit={2} next={3}" -f $name, $task.State, $task.Settings.ExecutionTimeLimit, $info.NextRunTime)
}

Write-Result "install done. First forced reboot is the next $RebootAt. Cancel a pending one with: shutdown /a"
exit 0
