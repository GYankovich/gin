# Ops: приёмка и миграция robots architecture

Дополнение к [ROBOTS-ARCHITECTURE-RELEASE_MAP.md](ROBOTS-ARCHITECTURE-RELEASE_MAP.md) §10.

## 1. Миграция config v3

### UI (один робот)

На странице `/robots` → настройки робота: если `config_version < 3`, в контекстной панели появляется кнопка **«Мигрировать config → v3»**.

API:

```http
POST /api/robots/migrate-config-v3
Content-Type: application/json

{ "robotId": 42 }
```

Без `robotId` — все trading-роботы (`type=2`) текущего пользователя.

### CLI (batch, все роботы в схеме)

Скрипт автоматически подхватывает `.env` из корня репозитория (даже при запуске из `backend/`).

```powershell
cd C:\Users\Asus\WebstormProject\gin
$env:PYTHONPATH = "backend"
python backend/scripts/migrate_robot_configs_v3.py --dry-run
python backend/scripts/migrate_robot_configs_v3.py
python backend/scripts/migrate_robot_configs_v3.py --robot-id 10
```

Если `DB_HOST=localhost` без `.env` — проверьте cwd или задайте переменные из `.env` вручную.

Перед prod: сделать backup `robots.config`, прогнать `--dry-run`, затем без флага.

## 2. Smoke checklist (E2E)

| # | Сценарий | Ожидание |
|---|----------|----------|
| 1 | MOEX robot: save → validate → live start | WS `init` с `broker_type=tinvest`, сигналы с `event_id`/`cycle_id` |
| 2 | Crypto testnet: create → crypto-screening → save → backtest | `allowed_symbols` заполнен, backtest KPI |
| 3 | Crypto testnet live | WS prices, order events с `decision_id` |
| 4 | Duplicate MOEX → crypto | Новый робот `broker_type=bybit`, universe сброшен |
| 5 | Portfolio type=1 bybit | Scheduler portfolio run → snapshot в БД |
| 6 | `GET /bybit/instruments?category=linear` | Список символов для UI |
| 7 | Legacy robot `config_version=2` | Кнопка migrate v3 → `schema_profile` + v3 |

## 3. Миграции БД

Убедиться, что применены:

- `0033` — `candles_cache.market`
- `0034` — `crypto_universe_daily`
- `bybit_funding_history` (R7)

```powershell
alembic upgrade head
```

## 4. Известные хвосты (не блокируют ops)

- `bybit_accounts` — не введена; snapshots в `portfolio_snapshots`
- Live funding accrual на perpetual — только backtest
- `openapi-typescript` — опционально
