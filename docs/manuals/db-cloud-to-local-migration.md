# Переезд облачной БД → локальная (public)

Инструкция по полному переносу данных из облачного Postgres (`ganaly` / `backtest`)
в локальную БД приложения (`public`), с пересозданием схемы через Alembic.

Скрипт: `backend/scripts/sync_cloud_to_local_db.py`

---

## 0. Перед стартом

1. Остановить backend / workers / uvicorn, чтобы не писали в локальную БД во время переноса.
2. Проверить доступы:
   - cloud Postgres (source),
   - local Postgres (target),
   - пользователь local имеет права `DROP/CREATE/TRUNCATE/INSERT` в `public`.
3. Обновить при необходимости `SOURCE_CONFIG` / `LOCAL_CONFIG` в скрипте
   (хост, порт, БД, пользователь, пароль).
4. Убедиться, что из корня репозитория работает:
   ```bash
   python -m alembic current
   ```
5. Зависимости: `psycopg2`, Alembic, `.env` с `DATABASE_URL` на **локальную** БД.

> Важно: cloud живёт в схемах `ganaly` + `backtest`, локально приложение ждёт таблицы в `public`.

---

## 1. Диагностика (без изменений)

```bash
python backend/scripts/sync_cloud_to_local_db.py --check-only
```

Смотрим:
- `alembic_version` source vs target,
- missing/extra tables/columns (source `ganaly|backtest` vs local `public`).

Ожидаемо: cloud revision может быть старой/другой; локальный head — актуальная цепочка миграций проекта.

---

## 2. Полный strict-перенос (очистка + миграции + данные)

```bash
python backend/scripts/sync_cloud_to_local_db.py --skip-check --strict
```

Скрипт делает:

1. **Drop** всех таблиц и sequences в local (кроме системных схем).
2. Создаёт схемы `ganaly` / `backtest` (нужны для старых шагов Alembic).
3. `alembic upgrade head` → структура в `public`.
4. Копирует **все** таблицы source:
   - совместимые → в канонические `public.<table>`,
   - несовместимые / коллизии имён → в mirror `public.<schema>__<table>`
     (пример: `public.ganaly__api_tokens`, `public.backtest__backtest_runs`).
5. Синхронизирует sequences по именам из source (best-effort).

Если `alembic upgrade head` падает — чиним миграции и повторяем шаг.
Типичные классы багов в цепочке:

- битый FK: `ForeignKey('"user".id')` / `source_, referent_` в `create_foreign_key`,
- битый SQL seed (`INSERT ... VALUES` без запятой),
- индекс по несуществующей колонке,
- `CREATE TABLE backtest.*` без заранее созданной схемы.

---

## 3. Влить mirror → канонические таблицы

После `--strict` часть данных лежит в `ganaly__*`. Чтобы приложение видело данные в обычных таблицах:

```bash
python backend/scripts/sync_cloud_to_local_db.py --strict-apply
```

Что делает:
- берёт `public.ganaly__*`,
- `TRUNCATE` канонических таблиц в dependency-aware порядке,
- `INSERT ... SELECT` по пересечению колонок,
- временно `session_replication_role = replica` (обход FK на время заливки),
- снова синхронизирует sequences из source.

Особый случай:
- `ganaly__users` **не** вливается в `public.user` (несовместимая форма; `login` NOT NULL).
  Данные остаются в mirror `public.ganaly__users`.
  Пользователи приложения — в `public.user` (из миграций / `ganaly.user`).

`backtest__*` collision-mirrors по умолчанию **не** вливаются в канон
(чтобы не затереть ganaly-версию одноимённых таблиц).

---

## 4. Обязательный пост-чек sequences

После `strict-apply` sequences часто **отстают** от `MAX(id)` в канонических таблицах
(потому что `INSERT ... SELECT` не двигает sequence, а `sync` с cloud может не совпасть
с локальным max после truncate/insert).

Симптом:

```
UniqueViolation: robot_execution_logs_pkey
Ключ "(id)=(...)" уже существует
```

Проверка и выравнивание всех serial/identity в `public`:

```sql
-- Пример для одной таблицы
SELECT
  COALESCE(MAX(id), 0) AS max_id,
  last_value,
  is_called
FROM robot_execution_logs, robot_execution_logs_id_seq;

SELECT setval(
  pg_get_serial_sequence('public.robot_execution_logs', 'id'),
  COALESCE((SELECT MAX(id) FROM public.robot_execution_logs), 0) + 1,
  false
);
```

Или прогнать аудит всех пар table↔sequence и для каждой с drift:

```sql
SELECT setval('<schema>.<seq>', <max_id> + 1, false);
```

Правило: **effective next** sequence должен быть `> MAX(id)`.

---

## 5. Сверка count source ↔ local

Для каждой source-таблицы (`ganaly` / `backtest`) сравнить `COUNT(*)` с:

- канонической `public.<table>`, и/или
- mirror `public.<schema>__<table>`.

Цель: `MATCH == число source-таблиц`, `DIFF == 0`.

Критерии успеха переезда:

| Проверка | Ожидание |
|---|---|
| `alembic upgrade head` | доходит до head без ошибок |
| row counts | все source-таблицы представлены в public (canonical или mirror) |
| `--strict-apply` | критичные таблицы (`api_tokens`, `robots`, `portfolio_*`, …) в каноне |
| sequences | нет drift относительно `MAX(id)` |
| smoke | логин / robots / portfolio_updater стартуют без UniqueViolation |

---

## 6. Рекомендуемый порядок команд (шпаргалка)

```bash
# 1) только смотрим
python backend/scripts/sync_cloud_to_local_db.py --check-only

# 2) полный перенос
python backend/scripts/sync_cloud_to_local_db.py --skip-check --strict

# 3) mirror → canonical
python backend/scripts/sync_cloud_to_local_db.py --strict-apply

# 4) выровнять sequences (аудит MAX(id) vs setval) — вручную / скриптом
# 5) smoke-тест приложения
```

Если шаг 2 оборвался на середине (drop уже выполнен, alembic упал):

```bash
python backend/scripts/sync_cloud_to_local_db.py --skip-check --strict
```

(`--skip-check` нужен, когда `alembic_version` ещё нет после drop.)

---

## 7. Известные грабли

1. **Схемы**: не восстанавливать cloud dump «как есть» в local — приложение на `public`.
2. **Коллизии имён** (`backtest_runs` и в `ganaly`, и в `backtest`):
   - ganaly → канон / `ganaly__*`,
   - backtest → `backtest__*`.
3. **Seed из миграций** (`dictionary`, `app_config`) конфликтует с copy → часть таблиц уходит в mirror, потом поднимается через `--strict-apply`.
4. **Windows + emoji в print миграций** → в скрипте выставляется `PYTHONIOENCODING=utf-8`.
5. После apply **обязательно** пересчитать sequences — иначе UniqueViolation на insert.

---

## 8. Rollback / безопасность

- Операция **разрушительная** для local: полный drop.
- Перед продом/общим стендом — snapshot / dump local.
- Cloud (source) скрипт только читает; не пишет.
- Пароли не коммитить в docs; держать в скрипте/секретах окружения.
