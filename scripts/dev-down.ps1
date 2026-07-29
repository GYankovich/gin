# Stop GIN dev stack: Vite (5173), API (8000), WS (8001), workers, esbuild children.
#
# Usage from repo root:
#   powershell -File scripts/dev-down.ps1

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$rootEsc = [Regex]::Escape($root)

Write-Host "Stopping GIN dev processes under $root ..."

$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.CommandLine -match $rootEsc
}

$ids = @($procs | ForEach-Object { $_.ProcessId } | Sort-Object -Unique)
if ($ids.Count -eq 0) {
    Write-Host "No matching processes."
} else {
    foreach ($procId in $ids) {
        $line = ($procs | Where-Object { $_.ProcessId -eq $procId } | Select-Object -First 1).CommandLine
        $short = if ($line.Length -gt 100) { $line.Substring(0, 100) + "..." } else { $line }
        Write-Host "  taskkill /F /T PID $procId — $short"
        taskkill /PID $procId /F /T 2>$null
    }
}

foreach ($port in @(5173, 8000, 8001)) {
    $listening = netstat -ano | Select-String ":$port\s" | Select-String "LISTENING"
    foreach ($line in $listening) {
        $parts = ($line -replace '\s+', ' ').Trim().Split(' ')
        if ($parts.Length -lt 5) { continue }
        $portPid = [int]$parts[-1]
        if ($portPid -le 0) { continue }
        Write-Host "  port :$port still held by PID $portPid — taskkill /F /T"
        taskkill /PID $portPid /F /T 2>$null
    }
}

Start-Sleep -Seconds 1
$busy = @()
foreach ($port in @(5173, 8000, 8001)) {
    if (netstat -ano | Select-String ":$port\s" | Select-String "LISTENING") {
        $busy += $port
    }
}
if ($busy.Count -eq 0) {
    Write-Host "[OK] Ports 5173, 8000, 8001 are free."
} else {
    Write-Host "[WARN] Still listening: $($busy -join ', ')"
}
