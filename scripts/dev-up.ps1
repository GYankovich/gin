# Dev: 4 Python processes (API, heavy worker, portfolio worker, WS gateway)
# PostgreSQL must be running. Apply migrations on first start.
#
# Usage from repo root:
#   powershell -File scripts/dev-up.ps1

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"

Write-Host "Starting GIN dev processes..."
Write-Host "  API:       python backend/run.py server"
Write-Host "  Heavy:     python backend/run.py worker --lane heavy"
Write-Host "  Portfolio: python backend/run.py worker --lane portfolio"
Write-Host "  WS:        python backend/run.py ws"
Write-Host ""
Write-Host "LIVE_EVENTS_BACKEND=postgres (default). Single-process fallback:"
Write-Host "  WORKER_EMBEDDED_ENABLED=true LIVE_EVENTS_BACKEND=memory"
Write-Host ""

# Не создаём отдельные командные окна:
# - `backend/run.py all` сам стартует API+workers+WS в подпроцессах
# - без CREATE_NEW_CONSOLE (см. backend/run.py)
cd '$root'
python backend/run.py all
