# Smoke-test crypto testnet backtest (token id=25)
# Запуск из корня репозитория в PowerShell:
#
#   $env:BYBIT_API_KEY = "your-key"
#   $env:BYBIT_API_SECRET = "your-secret"
#   .\backend\scripts\setup-crypto-testnet.ps1 -UserId 12

param(
    [int]$TokenId = 25,
    [Parameter(Mandatory = $true)][int]$UserId,
    [int]$Days = 3,
    [switch]$SkipBacktest
)

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path "$Root\.env")) {
    Write-Error ".env not found at $Root\.env"
}

Set-Location $Root
$env:PYTHONPATH = "backend"

if (-not $env:BYBIT_API_KEY -or -not $env:BYBIT_API_SECRET) {
    Write-Error "Set BYBIT_API_KEY and BYBIT_API_SECRET before running"
}

$argsList = @(
    "backend/scripts/setup_and_run_crypto_backtest.py",
    "--token-id", $TokenId,
    "--user-id", $UserId,
    "--days", $Days
)
if ($SkipBacktest) { $argsList += "--skip-backtest" }

python @argsList
exit $LASTEXITCODE
