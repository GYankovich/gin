# Start GIN after boot, before anyone logs in.
# Scheduled task GIN-Boot runs this as SYSTEM and stays alive while Python runs.
# Nginx is a separate task (GIN-Nginx): a short script must not parent nginx,
# or Task Scheduler kills it when the script exits.
#
#   powershell -File scripts/boot-gin.ps1
#   powershell -File scripts/boot-gin.ps1 -DryRun

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $Root "logs\boot"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$LogFile = Join-Path $LogDir "boot.log"

function Write-BootLog([string]$Message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Test-Listening([int]$Port) {
    $pattern = ":$Port\s+\S+\s+LISTENING"
    return [bool](netstat -ano | Select-String -Pattern $pattern)
}

function Resolve-GinPython {
    $candidates = @(
        (Join-Path $Root ".venv\Scripts\python.exe"),
        "C:\Users\GY\AppData\Local\Programs\Python\Python311\python.exe",
        "C:\Python314\python.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

Write-BootLog "boot-gin start (dryRun=$DryRun) root=$Root"

$postgres = Get-Service -Name "postgresql-x64-18" -ErrorAction SilentlyContinue
if ($postgres) {
    $deadline = (Get-Date).AddMinutes(3)
    while ($postgres.Status -ne "Running" -and (Get-Date) -lt $deadline) {
        Write-BootLog "waiting for postgresql-x64-18 ($($postgres.Status))"
        if (-not $DryRun) {
            Start-Service -Name "postgresql-x64-18" -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 3
        $postgres.Refresh()
    }
    Write-BootLog "postgresql-x64-18 status=$($postgres.Status)"
    if ($postgres.Status -ne "Running") {
        Write-BootLog "postgres is not running; continuing anyway"
    }
} else {
    Write-BootLog "postgresql-x64-18 service not found"
}

if (Test-Listening 8000) {
    Write-BootLog "API already listening on :8000, nothing to start"
    exit 0
}

$python = Resolve-GinPython
if (-not $python) {
    Write-BootLog "python.exe not found"
    exit 1
}
Write-BootLog "python=$python"

if ($DryRun) {
    Write-BootLog "dry-run: would start backend/run.py all"
    exit 0
}

$outLog = Join-Path $LogDir "backend.out.log"
$errLog = Join-Path $LogDir "backend.err.log"
# Truncate so a wedged previous run does not grow without bound.
Set-Content -Path $outLog -Value "$Stamp starting $python backend/run.py all" -Encoding UTF8
Set-Content -Path $errLog -Value $Stamp -Encoding UTF8

# Do not set GIN_ENV. Unset matches the current manual start and loads .env.
$proc = Start-Process `
    -FilePath $python `
    -ArgumentList @("backend\run.py", "all") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru

if (-not $proc) {
    Write-BootLog "failed to start python"
    exit 1
}
Set-Content -Path (Join-Path $LogDir "backend.pid") -Value $proc.Id -Encoding ASCII
Write-BootLog "backend supervisor pid=$($proc.Id); waiting"

Wait-Process -Id $proc.Id
$exitCode = $proc.ExitCode
if ($null -eq $exitCode) { $exitCode = 1 }
Write-BootLog "backend supervisor exited code=$exitCode"
exit $exitCode
