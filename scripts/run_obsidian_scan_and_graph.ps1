# Полный конвейер: Source Scanner (get-comments) + обновление графа Obsidian.
# Запуск из корня репозитория:
#   powershell -ExecutionPolicy Bypass -File scripts/run_obsidian_scan_and_graph.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

$Exe = Join-Path $RepoRoot "tools\get-comments\get-comments.exe"
if (-not (Test-Path $Exe)) {
    Write-Error "Не найден $Exe — скачайте get-comments (Source Scanner v2) в tools/get-comments/"
}

$Out = Join-Path $RepoRoot "scanner-output"
Remove-Item -Recurse -Force $Out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path @(
    (Join-Path $Out "backend"),
    (Join-Path $Out "alembic"),
    (Join-Path $Out "frontend-tsx"),
    (Join-Path $Out "frontend-ts")
) | Out-Null

& $Exe -dir (Join-Path $RepoRoot "backend\app") -work (Join-Path $Out "backend") -start "#///" -path "EPIC.ITEM.TOPIC" -ext ".py" -dest "md"
& $Exe -dir (Join-Path $RepoRoot "alembic") -work (Join-Path $Out "alembic") -start "#///" -path "EPIC.ITEM.TOPIC" -ext ".py" -dest "md"
& $Exe -dir (Join-Path $RepoRoot "frontend\src") -work (Join-Path $Out "frontend-tsx") -start "///@" -path "EPIC.ITEM.TOPIC" -ext ".tsx" -dest "md"
& $Exe -dir (Join-Path $RepoRoot "frontend\src") -work (Join-Path $Out "frontend-ts") -start "///@" -path "EPIC.ITEM.TOPIC" -ext ".ts" -dest "md"

python (Join-Path $RepoRoot "scripts\obsidian_graph_refresh.py") --vault $Out
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Готово: vault=$Out (открой в Obsidian). Graph/Index.md — вход в MOC."
