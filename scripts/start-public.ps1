# Production edge: nginx SSL → static dist/ + HTTP API :8000 + WS :8001
# Canonical URL: https://nefor.online  (ports 80/443)
# Fallback:      https://nefor.online:8443  (if ISP blocks 443)
# Docs: docs/DEPLOY-NEFOR.md
param(
    [switch]$SkipBuild,
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$NginxDir = Join-Path $Root "nginx"
$DistDir = Join-Path $Root "dist"
$Ports = @(80, 443, 8080, 8443)

Write-Host "=== GIN production (nginx + dist) ===" -ForegroundColor Cyan
Write-Host "Root: $Root"
Write-Host "Ports: $($Ports -join ', ')  (canonical https://nefor.online)"

if ($Build -or (-not $SkipBuild -and -not (Test-Path (Join-Path $DistDir "index.html")))) {
    Write-Host "[INFO] Building frontend (npm run build)..."
    Push-Location $Root
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $DistDir "index.html"))) {
    throw "dist/index.html missing. Run: npm run build"
}
Write-Host "[OK] dist/ ready"

function Ensure-FirewallRule([string]$Name, [int]$Port) {
    $existing = Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue
    if (-not $existing) {
        try {
            New-NetFirewallRule -DisplayName $Name -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile Any | Out-Null
            Write-Host "[OK] Firewall allow TCP $Port ($Name)"
        } catch {
            Write-Host "[WARN] Firewall rule $Name failed (run as Admin): $_"
        }
    } else {
        Write-Host "[OK] Firewall rule exists: $Name"
    }
}

Ensure-FirewallRule "GIN nginx HTTP 80" 80
Ensure-FirewallRule "GIN nginx HTTPS 443" 443
Ensure-FirewallRule "GIN nginx HTTP 8080" 8080
Ensure-FirewallRule "GIN nginx HTTPS 8443" 8443

$nginxExe = Join-Path $NginxDir "nginx.exe"
if (-not (Test-Path $nginxExe)) { throw "nginx.exe not found: $nginxExe" }

Push-Location $NginxDir
try {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $nginxExe -t 2>&1 | ForEach-Object { Write-Host $_ }
    $testOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev
    if (-not $testOk) { throw "nginx -t failed" }
    $nginxProc = Get-Process nginx -ErrorAction SilentlyContinue
    if ($nginxProc) {
        Write-Host "[INFO] Stopping nginx for listen update..."
        & $nginxExe -s stop 2>$null
        Start-Sleep -Seconds 1
        Get-Process nginx -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
    Write-Host "[INFO] Starting nginx..."
    Start-Process -FilePath $nginxExe -WorkingDirectory $NginxDir -WindowStyle Hidden
} finally {
    Pop-Location
}

Start-Sleep -Seconds 1
$listening = netstat -ano | Select-String "LISTENING" | Select-String ":443 "
if ($listening) {
    Write-Host "[OK] nginx listening on :443 (also :80, :8080, :8443)"
} else {
    Write-Host "[ERR] nginx not listening on :443 - check nginx/logs/error.log"
    if (Test-Path (Join-Path $NginxDir "logs\error.log")) {
        Get-Content (Join-Path $NginxDir "logs\error.log") -Tail 30
    }
    exit 1
}

Write-Host ""
Write-Host "Open: https://nefor.online" -ForegroundColor Green
Write-Host "Fallback: https://nefor.online:8443"
Write-Host "Keenetic: 80→80, 443→443 (and keep 8080/8443 as backup)"
Write-Host 'Need: $env:GIN_ENV="production"; python backend/run.py all'
Write-Host "Vite is NOT used in production (static dist/ only)."
