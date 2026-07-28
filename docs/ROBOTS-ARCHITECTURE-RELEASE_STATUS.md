# ROBOTS Architecture — Release Status

Источник плана: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md`.

## R1 — MOEX core hardening

### R1.1 — Live entry через orchestrator
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R1 → `R1.1`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §3.1, §9.1
- **Status**: ✅ done

#### Что сделано
- Добавлен `TradingOrchestrator.run_live_session()` как единая точка запуска live-сессии.
- `TradingScheduler` переведен на вызов orchestrator вместо прямого `create_trading_session()`.

#### Артефакты
- `backend/app/modules/robots/trading/runtime/orchestrator.py`
- `backend/app/modules/robots/trading/scheduler.py`

#### DoD (из release map)
- [x] Live path документирован (entrypoint: `TradingScheduler` → `TradingOrchestrator.run_live_session` → `TradingSession.run`)
- [x] Один entry point (scheduler больше не импортирует/не вызывает `create_trading_session`)

### R1.2 — TradingCore меньше связан с session
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R1 → `R1.2`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §4
- **Status**: ✅ done (фаза BRD-ARCH-04; подтверждено проверкой)

#### Что сделано
- Логика одного торгового цикла вынесена в `run_single_trading_cycle(host, cycle_count)` в `trading/core/trading_core.py`, host передается абстрактно.
- `TradingCore` — тонкая обёртка (`run_cycle(host, cycle_count)`), не содержит жестко зашитой логики `TradingSession`.
- Для вызовов DB, сигналов, ордеров, live-event'ов используются методы `host` (интерфейс), а не прямые импорты моделей/ORM/WS внутри `TradingCore`.

#### Артефакты
- `backend/app/modules/robots/trading/core/trading_core.py`
- `backend/tests/test_trading_core.py`

#### DoD (из release map)
- [x] `run_cycle` тестируется без полного `TradingSession`: используется легковесный `MagicMock` host в `test_trading_core.py`, без зависимостей на реальные сессии/БД/WS.

### R1.3 — Консолидация execution
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R1 → `R1.3`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §4.3
- **Status**: ✅ done

#### Что сделано
- Подтверждено, что runtime использует единый путь через `execution_service_for_session()` / `LiveExecutionService` (Stage6).
- Убран ре-экспорт legacy `LiveExecution` из `backend/app/modules/robots/trading/execution/__init__.py`, чтобы исключить случайное использование в prod.

#### Артефакты
- `backend/app/modules/robots/trading/execution/service.py`
- `backend/app/modules/robots/trading/execution/__init__.py`
- `backend/tests/test_execution_service.py`

#### DoD (из release map)
- [x] Нет prod-импортов `execution/live.py` через публичный пакет `trading.execution` (legacy `LiveExecution` не экспортируется).
- [x] Единый execution path подтвержден тестами `backend/tests/test_execution_service.py`.

### R1.4 — Удалить legacy unified_runner из prod
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R1 → `R1.4`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §11
- **Status**: ✅ done

#### Что сделано
- Проверено, что в `backend/app` нет прод-импортов и вызовов `unified_runner`/`run_unified_history_backtest`.
- Legacy-модуль `backend/app/modules/robots/trading/engines/unified_runner.py` оставлен как deprecated (docstring + `DeprecationWarning`) для parity/экспериментов.
- Прод-контур backtest/live остается на `TradingOrchestrator` + `TradingSession`/`BacktestTradingSession`.

#### Артефакты
- `backend/app/modules/robots/trading/engines/unified_runner.py` (deprecated legacy-only)
- `backend/app/modules/robots/trading/runtime/orchestrator.py`

#### DoD (из release map)
- [x] `unified_runner` не используется из prod-кода.
- [x] Legacy runtime smoke/regression зелёные (`backend/tests/test_unified_engine.py`, `backend/tests/test_trading_orchestrator.py`).

### R1.5 — `broker_type` immutable
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R1 → `R1.5`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §15
- **Status**: ✅ done

#### Что сделано
- В `RobotService.update_robot()` добавлена проверка: если patch меняет `config.broker_type` относительно текущего робота, возвращается `HTTP 409 Conflict`.
- В `RobotService.update_robot_config()` добавлена аналогичная проверка для полного обновления конфига.
- Для `/api/robots/update` и `/api/robots/config` добавлены `409` responses в OpenAPI-описание (конфликт immutable broker).

#### Артефакты
- `backend/app/modules/robots/service.py`
- `backend/app/modules/robots/router.py`
- `backend/tests/test_robot_service_broker_immutability.py`

#### DoD (из release map)
- [x] `POST /update` возвращает `409` при попытке сменить `broker_type`.
- [x] `POST /config` возвращает `409` при попытке сменить `broker_type`.
- [x] Pytest покрытие добавлено (`backend/tests/test_robot_service_broker_immutability.py`).
- [x] OpenAPI отражает `409` для соответствующих endpoint-ов.

### R1.6 — WS envelope на frontend
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R1 → `R1.6`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §7.7
- **Status**: ✅ done

#### Что сделано
- В `LivePage` убрана client-only генерация id для feed-событий через `signalIdRef`.
- Ленты сигналов/ордеров переведены на WS envelope ключи (`event_id` + `run_id`/`cycle_id`/`decision_id`) для стабильной идентификации событий.
- Добавлен безопасный fallback-ключ для старого/неполного payload без envelope полей.

#### Артефакты
- `frontend/src/pages/LivePage.tsx`

#### DoD (из release map)
- [x] Frontend использует envelope-поля (`event_id`, `run_id`, `cycle_id`, `decision_id`) в потоке `/ws/live`.
- [x] Нет client-only `signalIdRef` для идентификации/дедупа feed-событий.
- [x] Frontend build green (`npm run build`).

### R1.7 — `data_provider/` → единый `data/` (MOEX MarketDataFacade)
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R1 → `R1.7`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §4.2
- **Status**: ✅ done

#### Что сделано
- В прод-ходах MOEX используется единый market-data слой через `app.modules.robots.trading.data.get_market_data_facade()` (`MarketDataFacade`).
- Legacy-пакет `backend/app/modules/robots/trading/data_provider/*` остаётся только частью legacy unified-engine контуров (`trading/engines/unified_runner.py`, `trading/engines/context.py`) и тестов (`backend/tests/test_unified_engine.py`).

#### Артефакты
- `backend/app/modules/robots/trading/data/` (активный прод stack: `MarketDataFacade`)
- `backend/app/modules/robots/trading/data_provider/` (legacy only)
- `backend/app/modules/robots/trading/backtest/dms_emulator.py` — docstring обновлен, чтобы не направлять “новые места кода” на `data_provider`

#### DoD (из release map)
- [x] В прод-коде MOEX используется `MarketDataFacade` (проверка по импорто-пути `trading.data.*`).
- [x] Legacy `data_provider` не используется в runtime MOEX pipeline (остаётся legacy/unified-engine/test-only).

## R2 — Config v3 и typed profiles (MOEX)

### R2.1 — Profile registry backend
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R2 → `R2.1`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §17.5
- **Status**: ✅ done (registry foundation)

#### Что сделано
- Добавлен backend profile registry в `backend/app/modules/robots/config/profiles/`:
  - `PROFILE_REGISTRY`
  - `resolve_schema_profile(...)`
  - `validate_robot_config(...)`
  - `dump_robot_config(...)`
- Добавлен профиль `type2_tinvest` (bridge на основе текущей v2-схемы `TradingRobotConfigV2`) для поэтапного перехода к v3 typed profiles.
- Текущая сервисная валидация (`RobotService._validate_robot_config`) переведена на registry API вместо прямого `ensure_config_v2 + GrainSeedConfig.model_validate`.
- Публичный re-export новых API добавлен в `backend/app/modules/robots/config/__init__.py`.

#### Артефакты
- `backend/app/modules/robots/config/profiles/__init__.py`
- `backend/app/modules/robots/config/profiles/type2_tinvest.py`
- `backend/app/modules/robots/config/__init__.py`
- `backend/app/modules/robots/service.py`
- `backend/tests/test_config_profiles.py`

#### DoD (из release map)
- [x] Есть `validate_robot_config()` как единая точка profile-based валидации backend config.
- [x] `PROFILE_REGISTRY` содержит `type2_tinvest` профиль.
- [x] Существующий v2-контур и миграция совместимы (регресс по `test_config_migration.py` зелёный).
- [x] Тесты profile-registry добавлены (`backend/tests/test_config_profiles.py`).

### R2.2 — Typed `MoexRiskConfig`, `MoexCostsConfig`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R2 → `R2.2`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §17.3
- **Status**: ✅ done

#### Что сделано
- Добавлены typed-модели MOEX-конфига:
  - `backend/app/modules/robots/config/risk_moex.py` → `MoexRiskConfig`
  - `backend/app/modules/robots/config/costs_moex.py` → `MoexCostsConfig`
- Профиль `type2_tinvest` переведен на typed-поля:
  - `risk: MoexRiskConfig`
  - `costs: MoexCostsConfig`
- Обновлены экспорты `backend/app/modules/robots/config/__init__.py` для новых typed-моделей.

#### Артефакты
- `backend/app/modules/robots/config/risk_moex.py`
- `backend/app/modules/robots/config/costs_moex.py`
- `backend/app/modules/robots/config/profiles/type2_tinvest.py`
- `backend/app/modules/robots/config/__init__.py`
- `backend/tests/test_config_profiles.py`

#### DoD (из release map)
- [x] Typed `MoexRiskConfig` и `MoexCostsConfig` подключены в backend profile `type2_tinvest`.
- [x] Round-trip тест на сохранение falsy-значений добавлен (`test_dump_preserves_falsy_flags`).
- [x] Регресс миграции v2 не сломан (`test_config_migration.py` зелёный).

### R2.3 — `POST /validate-config`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R2 → `R2.3`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §17.7
- **Status**: ✅ done

#### Что сделано
- Добавлен endpoint `POST /api/robots/validate-config`:
  - принимает `robot_type`, `broker_type`, `config`
  - валидирует через profile-registry
  - возвращает `schema_profile` + `normalized_config` без записи в БД
- Добавлены новые схемы:
  - `RobotValidateConfigRequest`
  - `RobotValidateConfigResponse`
- В сервисе добавлен `validate_robot_config_payload(...)`:
  - success → нормализованный payload
  - validation error → `HTTP 422 Unprocessable Entity`
- В OpenAPI для endpoint добавлен явный `422` response.

#### Артефакты
- `backend/app/modules/robots/router.py`
- `backend/app/modules/robots/service.py`
- `backend/app/modules/robots/schemas.py`
- `backend/tests/test_robot_service_validate_config.py`

#### DoD (из release map)
- [x] `POST /validate-config` возвращает 200 с нормализованным config.
- [x] `POST /validate-config` возвращает 422 при ошибках валидации.
- [x] Тесты добавлены (`test_robot_service_validate_config.py`) + регресс profile-тестов зелёный.

### R2.4 — `POST /migrate-config-v3`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R2 → `R2.4`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §17.8
- **Status**: ✅ done (backend endpoint + migration helpers)

#### Что сделано
- Добавлена v3-миграция в `config/migration.py`:
  - `CONFIG_VERSION_V3 = 3`
  - `resolve_schema_profile_v3(...)`
  - `migrate_v2_to_v3(raw, robot_type, broker_type)` — поверх `ensure_config_v2`
- Добавлены схемы запроса/ответа:
  - `RobotMigrateConfigV3Request`
  - `RobotMigrateConfigV3Item`
  - `RobotMigrateConfigV3Response`
- Добавлен endpoint:
  - `POST /api/robots/migrate-config-v3` → батч-миграция всех (или одного) trading-робота пользователя
  - выставляет `config_version: 3` и `schema_profile` (сейчас `type2_tinvest` для MOEX)
- В `RobotService` добавлен `migrate_trading_robots_config_v3(...)` по аналогии с v2:
  - читает текущий config
  - вызывает `migrate_v2_to_v3`
  - обновляет `robots.config` при изменениях

#### Артефакты
- `backend/app/modules/robots/config/migration.py`
- `backend/app/modules/robots/config/__init__.py`
- `backend/app/modules/robots/schemas.py`
- `backend/app/modules/robots/service.py`
- `backend/app/modules/robots/router.py`
- `backend/tests/test_config_migration.py`

#### DoD (из release map)
- [x] `migrate_v2_to_v3` проставляет `config_version: 3` + корректный `schema_profile`.
- [x] Endpoint `POST /migrate-config-v3` реализован и использует migration helper.
- [x] Тесты миграции v3 добавлены и зелёные.

### R2.5 — `GET /config-schema/{profile}`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R2 → `R2.5`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §17.7
- **Status**: ✅ done

#### Что сделано
- Добавлен helper `export_config_schema(schema_profile)` в profile registry:
  - возвращает `model_json_schema()` для профиля из `PROFILE_REGISTRY`
  - `KeyError` для неизвестного профиля
- Добавлен endpoint `GET /api/robots/config-schema/{schema_profile}`:
  - auth required
  - `200` → `{ schema_profile, json_schema }`
  - `404` для неизвестного профиля
- Схема ответа: `RobotConfigSchemaResponse`
- Тесты: `test_export_config_schema_type2_tinvest`, `test_export_config_schema_unknown_profile_raises`

#### Артефакты
- `backend/app/modules/robots/config/profiles/__init__.py`
- `backend/app/modules/robots/config/__init__.py`
- `backend/app/modules/robots/schemas.py`
- `backend/app/modules/robots/router.py`
- `backend/tests/test_config_profiles.py`

#### DoD (из release map)
- [x] JSON Schema export для `type2_tinvest` доступен через REST.
- [x] UI/IDE может подгрузить схему по `schema_profile`.

### R2.6 — Frontend MOEX typed
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R2 → `R2.6`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §17.6 T2
- **Status**: ✅ done (typed MOEX config + «Проверить» через validate-config)

#### Что сделано
- Создан модуль `frontend/src/modules/robots/config/`:
  - `types/type2-tinvest.ts` — `Type2TinvestConfig` (v3)
  - `types/profiles.ts` — discriminated union + type guard
  - `resolveProfile.ts` — `resolveSchemaProfile`, `resolveSchemaProfileFromDraft`
  - `builders/buildMoexConfig.ts` — сборка v3 config (`config_version: 3`, `schema_profile`, `instrument_id_type`)
  - `validate/collectIssues.ts` — typed `collectIssues` / `ConfigValidationIssue`
- `robotSettingsValidation.ts` — thin re-export для обратной совместимости
- `robotService`: `validateConfig`, `getConfigSchema`
- `TradingRobotSettingsPage`:
  - сохранение через `buildMoexConfig` для `type2_tinvest`
  - «Проверить» вызывает `POST /validate-config` после локальных проверок

#### Артефакты
- `frontend/src/modules/robots/config/**`
- `frontend/src/pages/robots/robotSettingsValidation.ts`
- `frontend/src/services/robotService.ts`
- `frontend/src/pages/TradingRobotSettingsPage.tsx`

#### DoD (из release map)
- [x] `resolveSchemaProfile` + `buildMoexConfig` + typed `collectIssues`
- [x] «Проверить» использует backend `validate-config` для MOEX trading robot
- [x] `npm run build` проходит

### R2.7 — `deriveMarketProfile` (MOEX branch)
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R2 → `R2.7`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §8.1.1
- **Status**: ✅ done

#### Что сделано
- В `resolveProfile.ts` добавлены:
  - `deriveMarketProfile` / `deriveMarketProfileFromDraft` → `'portfolio' | 'moex' | 'crypto'`
  - `isMoexType2TinvestDraft` — MOEX pipeline UI только для `type2_tinvest`
- `TradingRobotSettingsPage`: панели П1/П2/DMS preview привязаны к `isMoexType2Tinvest`
- `derivePipelineVisualizerNodes`: П1/П2 в навигаторе только для MOEX `type2_tinvest`

#### Артефакты
- `frontend/src/modules/robots/config/resolveProfile.ts`
- `frontend/src/pages/TradingRobotSettingsPage.tsx`
- `frontend/src/pages/robots/derivePipelineVisualizerNodes.ts`

#### DoD (из release map)
- [x] MOEX panels (П1/П2/DMS) показываются только для `type2_tinvest`
- [x] `deriveMarketProfile` реализован по target §8.1.1

### R2.8 — `broker_type` read-only в UI
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R2 → `R2.8`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §15.3
- **Status**: ✅ done

#### Что сделано
- Добавлен `frontend/src/modules/robots/config/brokerImmutability.ts`:
  - `isBrokerTypeLocked(robotId)` — lock после создания
  - `BROKER_CHANGE_BLOCKED_MESSAGE` — текст toast
  - `isBrokerTypeConflictError` — распознавание HTTP 409 от API
- `TradingRobotSettingsPage`: поле «Брокер» disabled для существующего робота + hint; toast при попытке смены; обработка 409 при save
- `TestingRobotParamsCard` / `TestingPageContent`: broker select locked при выбранном `robotId`

#### Артефакты
- `frontend/src/modules/robots/config/brokerImmutability.ts`
- `frontend/src/pages/TradingRobotSettingsPage.tsx`
- `frontend/src/pages/testing/TestingRobotParamsCard.tsx`
- `frontend/src/pages/testing/TestingPageContent.tsx`

#### DoD (из release map)
- [x] Поле «Брокер» read-only после `robot.id`
- [x] Toast: «Для смены брокера создайте нового робота»
- [x] `npm run build` проходит

---

## Этап R2 — итог

**Статус этапа:** ✅ завершён (R2.1–R2.8)

**Критерий из release map:** новый MOEX trading robot сохраняется как `config_version: 3`, `schema_profile: type2_tinvest`; validate без save работает.

**Следующий этап:** R3 — единая схема кэша свечей (`candles_cache` + `market` column).

---

## Этап R3 — прогресс

### R3.1 — Alembic migration (`candles_cache` schema)
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R3 → `R3.1`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §6.2.1
- **Status**: ✅ done

#### Что сделано
- Добавлена миграция `0033_candles_cache_market_schema.py`:
  - новые колонки: `market`, `instrument_id`, `source`
  - удалён legacy unique/index по `(ticker, interval, candle_time)`
  - создан новый уникальный индекс: `(market, instrument_id, interval, candle_time)`
  - добавлен обычный индекс под тот же порядок полей
- Реализованы `upgrade`/`downgrade`.

#### DoD (из release map)
- [x] Migration up/down для новой ключевой схемы.

### R3.2 — Backfill MOEX rows
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R3 → `R3.2`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §6.2.1
- **Status**: ✅ done

#### Что сделано
- В `upgrade` миграции добавлен backfill legacy-данных:
  - `market = 'moex'`
  - `instrument_id = ticker`
  - `source = 'legacy_moex'`
- После backfill выставлены `NOT NULL` на `market`, `instrument_id`, `source`.

#### DoD (из release map)
- [x] Legacy строки заполнены MOEX discriminator-полями.

### R3.3 — ORM `CandleCache`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R3 → `R3.3`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §6.2.1
- **Status**: ✅ done

#### Что сделано
- `backend/app/modules/dms/models.py`:
  - `CandleCache` дополнен полями `market`, `instrument_id`, `source`
  - обновлены unique/index на новый ключ.

#### DoD (из release map)
- [x] ORM соответствует новой схеме таблицы.

### R3.4 — `db_cache.py` + facade reads
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R3 → `R3.4`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §16.3
- **Status**: ✅ done

#### Что сделано
- `query_candles_cache_rows(...)` переведён на фильтрацию по `market + instrument_id`.
- `BacktestMoexMarketDataFacade.read_candles_cache_rows(...)` расширен параметрами `market`, `instrument_id`.
- В `DmsService`:
  - upsert в `candles_cache` пишет `market/instrument_id/source`
  - `ON CONFLICT` обновлён на новый ключ
  - внутренние выборки свечей и ATR (`D1`) используют `market='moex'` + `instrument_id`.

#### Проверка
- `pytest tests/test_market_data_facade.py -q` → 5 passed
- `pytest tests/test_db_cache_market_key.py -q` → 1 passed
- `pytest tests/test_moex_snapshots.py -q` → 1 passed

#### DoD (из release map)
- [x] `db_cache.py` и facade reads фильтруют `candles_cache` по `market`.
- [x] Покрыто unit-тестами чтения нового ключа.

### R3.5 — Prefetch / П1 paths (`market=moex`)
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R3 → `R3.5`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §16.4
- **Status**: ✅ done

#### Что сделано
- В history-backtest legacy reads из `candles_cache` (`RobotService`) передаётся явный `market='moex'` и `instrument_id`.
- `DmsService` prefetch/ATR-path (`_ensure_candles_cached_for_tickers`, `_load_atr_percent_map`) использует `market='moex'` + `instrument_id`.
- Upsert свечей (`_upsert_candles_cache`) пишет `market='moex'` по умолчанию и `instrument_id=ticker`, что делает П1/Prefetch консистентным с новой схемой.

#### Проверка
- `pytest tests/test_universe_jobs.py -q` → 3 passed
- `pytest tests/test_market_data_facade.py tests/test_db_cache_market_key.py tests/test_universe_jobs.py -q` → 9 passed

#### DoD (из release map)
- [x] Prefetch и П1 paths работают с discriminator `market=moex`.
- [x] Регрессии по universe jobs зелёные.

---

## Этап R3 — итог

**Статус этапа:** ✅ завершён (R3.1–R3.5)

**Критерий из release map:** MOEX backtest и П1 работают на новой схеме; коллизии тикеров MOEX/crypto исключены на уровне БД.

---

## Этап R4 — прогресс

### R4.1 — ByBit REST v5 client
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R4 → `R4.1`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §3.3
- **Status**: ✅ done

#### Что сделано
- Добавлен модуль `backend/app/modules/bybit/`:
  - `signer.py` — HMAC-подпись приватных запросов ByBit v5 (`X-BAPI-*`)
  - `http_client.py` — async REST client с поддержкой:
    - `get_kline(...)` (public, `/v5/market/kline`)
    - `get_wallet_balance(...)` (private, `/v5/account/wallet-balance`)
    - `get_instruments_info(...)`, `get_server_time(...)`
  - `__init__.py` — экспорт клиента/ошибки/signer
- Реализован безопасный default для среды: `testnet=True` (`api-testnet.bybit.com`).
- Обработка ошибок:
  - HTTP status >= 400 → `BybitApiError`
  - `retCode != 0` → `BybitApiError` с кодом API.

#### Проверка
- Добавлены тесты `backend/tests/test_bybit_http_client.py`:
  - подпись signer
  - canonical body
  - testnet base URL
  - public kline call
  - private wallet-balance (negative + positive сценарии)
- `pytest tests/test_bybit_http_client.py -q` → 6 passed

#### DoD (из release map)
- [x] `modules/bybit/http_client.py`, `modules/bybit/signer.py` реализованы.
- [x] Testnet сценарии `balance + kline` покрыты тестами.

### R4.2 — ByBit WebSocket
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R4 → `R4.2`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §3.3
- **Status**: ✅ done

#### Что сделано
- Добавлен `backend/app/modules/bybit/websocket.py`:
  - `BybitWebSocketClient` (public stream)
  - `kline_topic(symbol, interval)` для стандартизированных топиков
  - `parse_kline_event(payload)` с нормализацией в `BybitKlineEvent`
  - auto-pong на ping-сообщения
- Обновлён экспорт модуля в `backend/app/modules/bybit/__init__.py`.

#### Проверка
- Добавлены тесты `backend/tests/test_bybit_websocket.py`:
  - builder топиков
  - парсинг kline payload
  - subscribe + recv + ping/pong flow
- `pytest tests/test_bybit_websocket.py tests/test_bybit_http_client.py -q` → 9 passed

#### DoD (из release map)
- [x] `modules/bybit/websocket.py` реализован.
- [x] Public kline stream покрыт unit-тестами.

### R4.3 — `ByBitBrokerFacade`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R4 → `R4.3`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §4.1
- **Status**: ✅ done

#### Что сделано
- Добавлен `backend/app/modules/robots/trading/brokers/bybit.py`:
  - реализация `BrokerFacade` для `broker_type=bybit`
  - REST методы foundation уровня:
    - `get_accounts`, `get_portfolio`, `get_free_funds`, `get_candles`
  - WS методы:
    - `connect_websocket`, `subscribe_prices`, `unsubscribe_prices`, `get_last_price`, `close_websocket`
    - внутренний receiver loop на основе `BybitWebSocketClient` + fanout в очереди
- Trading-операции (`post_order`, `cancel_order`, etc.) помечены `NotImplementedError` до R6 (live execution этап).

#### Проверка
- Добавлены тесты `backend/tests/test_bybit_broker_facade.py`:
  - получение accounts/free_funds
  - mapping kline → candles
- В составе общего прогона ByBit foundation:
  - `pytest tests/test_broker_routing.py tests/test_bybit_broker_facade.py tests/test_bybit_http_client.py tests/test_bybit_websocket.py -q` → 17 passed

#### DoD (из release map)
- [x] `ByBitBrokerFacade` реализует текущий `BrokerFacade` контракт для foundation-части.

### R4.4 — Factory + routing (`bybit`)
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R4 → `R4.4`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §4.1
- **Status**: ✅ done

#### Что сделано
- Обновлён routing:
  - `SUPPORTED_LIVE_BROKERS` включает `bybit`
  - `live_market_data_provider("bybit") -> "bybit_market"`
- Обновлён factory:
  - `create_broker_facade("bybit", token)` возвращает `ByBitBrokerFacade`
- Расширены тесты `backend/tests/test_broker_routing.py`:
  - supported live broker для `bybit`
  - provider routing для `bybit_market`
  - factory creation `ByBitBrokerFacade`

#### DoD (из release map)
- [x] Routing/factory поддерживают `broker_type=bybit`.
- [x] Тесты роутинга и фабрики расширены и зелёные.

### R4.5 — `bybit_market` provider
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R4 → `R4.5`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §4.2
- **Status**: ✅ done

#### Что сделано
- Добавлен `backend/app/modules/robots/trading/data/providers/bybit_market.py`:
  - `ensure_candles_bybit_market(...)` для загрузки historical kline из ByBit
  - нормализация kline rows
  - upsert в `candles_cache` с ключом:
    - `market='bybit'`
    - `instrument_id=symbol`
    - `source='bybit_kline_api'`
- Провайдер экспортирован в `providers/__init__.py`.

#### Проверка
- Добавлены тесты `backend/tests/test_bybit_market_provider.py`:
  - interval mapping to ByBit
  - запись свечей в `candles_cache` path (mock DB)
- В составе общего прогона foundation:
  - `pytest tests/test_bybit_market_provider.py ... tests/test_intervals.py -q` → 24 passed

#### DoD (из release map)
- [x] `ensure_candles`-путь для ByBit реализован с записью `market=bybit`.

### R4.6 — Intervals ByBit
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R4 → `R4.6`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §4.2.1
- **Status**: ✅ done

#### Что сделано
- В `backend/app/modules/robots/trading/intervals.py` добавлен mapping к ByBit kline:
  - `strategy_interval_to_bybit_kline(raw|ResolvedInterval) -> str`
  - поддержаны `1/3/5/15/30/60/120/240/D/W/M`
  - fallback на `"5"` для неподдержанных значений.

#### Проверка
- Тесты маппинга в `backend/tests/test_bybit_market_provider.py` + регрессы `test_intervals.py` зелёные.

#### DoD (из release map)
- [x] Интервалы стратегии маппятся в формат ByBit kline (`5m`, `1h`, etc. через ByBit API codes).

### R4.7 — API tokens для ByBit
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R4 → `R4.7`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §5.3
- **Status**: ✅ done

#### Что сделано
- Backend `settings` (`/apikey`) расширен для ByBit credentials:
  - `ApiKeyCreate` поддерживает `token_secret`, `testnet`, `account_type`
  - `ApiKeyResponse` возвращает `extra_data`
  - новый endpoint `POST /api/apikey/test` для проверки ключа без сохранения
- В `ApiKeyService`:
  - добавлен `test_key(...)`:
    - `tinvest` → проверка через `create_tbank_client().get_accounts()`
    - `bybit` → проверка private endpoint `get_wallet_balance(...)`
  - `create_key(...)` переведён в async и валидирует ключ до сохранения
  - `extra_data` сохраняется в `api_tokens.extra_data` (JSONB)
- Frontend `SettingsPage`:
  - для ByBit типа токена показываются поля `API Secret`, `account type`, `testnet/mainnet`
  - кнопка «Проверить» вызывает `POST /apikey/test`
  - сохранение отправляет ByBit-параметры в backend.

#### Проверка
- Добавлены тесты `backend/tests/test_settings_api_key_service.py` (ByBit validation path).
- Общий прогон R4:
  - `pytest tests/test_settings_api_key_service.py tests/test_broker_routing.py tests/test_bybit_broker_facade.py tests/test_bybit_http_client.py tests/test_bybit_websocket.py tests/test_bybit_market_provider.py tests/test_intervals.py -q` → 26 passed
- Frontend: `npm run build` → OK

#### DoD (из release map)
- [x] API tokens path поддерживает ByBit credentials.
- [x] Проверка/валидация ключа перед сохранением реализована.

---

## Этап R4 — прогресс

- [x] R4.1 ByBit REST v5 client
- [x] R4.2 ByBit WebSocket
- [x] R4.3 ByBitBrokerFacade
- [x] R4.4 Factory + routing (`bybit`)
- [x] R4.5 bybit_market provider
- [x] R4.6 Intervals ByBit
- [x] R4.7 API tokens для ByBit

---

## Этап R4 — итог

**Статус этапа:** ✅ завершён (R4.1–R4.7)

**Checkpoint из release map:** testnet balance, kline fetch, запись в `candles_cache(market=bybit)` — реализованы.

---

---

## R5 — Crypto universe и portfolio ByBit

### R5.1 — `crypto_universe.py`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R5 → `R5.1`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §3.3.1
- **Status**: ✅ done

#### Что сделано
- Добавлен модуль `backend/app/modules/robots/crypto_universe.py`:
  - `score_bybit_tickers(...)` — фильтрация по ликвидности и спреду;
  - `rebuild_crypto_universe(...)` — пересчёт `allowed_symbols` и запись в `robots.config`;
  - поддержаны настраиваемые фильтры из `config.crypto_universe` (`min_turnover_24h_usd`, `max_spread_pct`, `limit`, `category`, `quote_coin`).

#### Проверка
- Добавлены unit-тесты `backend/tests/test_crypto_universe.py` с mock-тикерами и проверкой обновления `allowed_symbols`.

#### DoD (из release map)
- [x] Volume/spread filtering реализован.
- [x] Unit test с mock tickers добавлен.

### R5.2 — `rebuild_crypto_universe` job
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R5 → `R5.2`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §4.4
- **Status**: ✅ done

#### Что сделано
- В `backend/app/modules/robots/universe_jobs.py` добавлен `rebuild_crypto_screening(...)`.
- В `backend/app/modules/robots/service.py` добавлен `run_crypto_screening_job(...)`.
- Job сохраняет результат в `robots.config` (JSONB), включая `allowed_symbols`.

#### DoD (из release map)
- [x] Hook в `universe_jobs.py` добавлен.
- [x] Пишет `allowed_symbols` в config JSONB.

### R5.3 — `POST /jobs/crypto-screening`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R5 → `R5.3`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §7.5
- **Status**: ✅ done

#### Что сделано
- В `backend/app/modules/robots/router.py` добавлен endpoint:
  - `POST /api/robots/jobs/crypto-screening`
- В `backend/app/modules/robots/schemas.py` добавлена схема ответа:
  - `RobotCryptoScreeningResponse` (`symbols`, `accepted`, `scanned`, `message`, `skipped`).

#### DoD (из release map)
- [x] Endpoint возвращает `200`.
- [x] Возвращается preview-symbols (`symbols`).

### R5.4 — `crypto_universe_daily` table
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R5 → `R5.4`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §6.5
- **Status**: ✅ done

#### Что сделано
- Добавлена миграция `alembic/versions/0034_crypto_universe_daily.py`:
  - новая таблица `{schema}.crypto_universe_daily`;
  - уникальность `(robot_id, trade_date, symbol)`;
  - индексы по `(robot_id, trade_date)` и `filter_result`.
- Добавлена ORM-модель `CryptoUniverseDaily` в `backend/app/modules/dms/models.py` (аналог `DailyUniverse` для crypto branch).
- В `backend/app/modules/robots/crypto_universe.py` добавлена запись результатов screening в `crypto_universe_daily`:
  - daily refresh (delete-by-date + upsert accepted symbols),
  - сохранение основных метрик (`turnover_24h`, `last_price`, `spread_percent`, `meta_payload`).

#### DoD (из release map)
- [x] Alembic migration добавлена.
- [x] Таблица используется как аналог `daily_universe` для crypto-screening.

### R5.5 — Config `type2_bybit` schema
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R5 → `R5.5`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §17.4
- **Status**: ✅ done

#### Что сделано
- Добавлен профиль `backend/app/modules/robots/config/profiles/type2_bybit.py`:
  - `Type2BybitConfig`,
  - `BybitBrokerConfig`,
  - `CryptoUniverseConfig`,
  - `CryptoSignalGenerationConfig`.
- Добавлены typed-блоки:
  - `backend/app/modules/robots/config/risk_crypto.py` → `CryptoRiskConfig`,
  - `backend/app/modules/robots/config/costs_crypto.py` → `CryptoCostsConfig`.
- Обновлён profile registry `backend/app/modules/robots/config/profiles/__init__.py`:
  - добавлен `type2_bybit` в `PROFILE_REGISTRY`,
  - `resolve_schema_profile(...)` теперь поддерживает `(robot_type=2, broker_type=bybit)`.
- Обновлены exports в `backend/app/modules/robots/config/__init__.py`.

#### Проверка
- Обновлены тесты `backend/tests/test_config_profiles.py`:
  - registry/resolve для `type2_bybit`,
  - validate + dump для ByBit профиля,
  - export schema `type2_bybit`.

#### DoD (из release map)
- [x] Профиль `type2_bybit` реализован.
- [x] Содержит `crypto_universe` и `bybit.*` блоки.

### R5.6 — Portfolio `type=1` + bybit
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R5 → `R5.6`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §5.1
- **Status**: ✅ done

#### Что сделано
- `backend/app/modules/robots/portfolio_updater/robot.py`:
  - добавлена ветка выполнения для `broker_type=bybit`,
  - получение unified account/portfolio через `ByBitBrokerFacade`,
  - нормализация wallet balance в формат snapshot и сохранение в `portfolio_snapshots`.
- `backend/app/modules/robots/portfolio_updater/queries.py`:
  - scheduler query теперь возвращает `broker_type` и `token_extra_data`.
- `backend/app/modules/robots/portfolio_updater/scheduler.py`:
  - передаёт в robot `broker_type` и `token_extra_data` (для `token_secret`, `testnet`).
- Добавлен тест `backend/tests/test_portfolio_bybit_robot.py` (нормализация ByBit портфеля в snapshot shape).

#### DoD (из release map)
- [x] Portfolio updater поддерживает `type=1` с `broker_type=bybit`.
- [x] Сохраняются snapshots unified account.

### R5.7 — `type1_bybit` profile
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R5 → `R5.7`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §17.4
- **Status**: ✅ done

#### Что сделано
- Добавлены profile-схемы:
  - `backend/app/modules/robots/config/profiles/type1_bybit.py`,
  - `backend/app/modules/robots/config/profiles/type1_tinvest.py`.
- `PROFILE_REGISTRY` и `resolve_schema_profile(...)` расширены профилями:
  - `type1_tinvest`,
  - `type1_bybit`.
- В `update_robot_config(...)` добавлена profile-валидация и нормализация для `robot.type=1` перед сохранением.
- Расширены тесты `backend/tests/test_config_profiles.py`:
  - registry/resolve/validate/export для `type1_bybit`.

#### DoD (из release map)
- [x] `profiles/type1_bybit.py` реализован.
- [x] Profile-based validate on save для `type=1` включен.

---

## Этап R5 — итог

**Статус этапа:** ✅ завершён (R5.1–R5.7)

**Критерий из release map:** portfolio robot на testnet синхронизирует баланс; screening job заполняет `allowed_symbols`.

---

## R6 — Crypto trading live

### R6.1 — Live session + bybit config
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R6 → `R6.1`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §9.2
- **Status**: ✅ done

#### Что сделано
- Обновлён `backend/app/modules/robots/trading/session.py`:
  - `TradingSession` теперь читает bybit-ветку конфига из `signal_generation` и `allowed_symbols/instruments`,
  - live-цикл остается в том же `TradingSession` (без отдельного `ByBitTradingSession`),
  - добавлен scheduled `crypto_universe` refresh (через `run_crypto_screening_job`) для `broker_type=bybit`.
- Обновлён `backend/app/modules/robots/trading/brokers/bybit.py`:
  - `get_portfolio(...)` теперь отдает нормализованный payload (`total_amount_portfolio`, `positions`, `free_funds`) совместимый с общими stage-пайпами.
- Добавлены тесты:
  - `backend/tests/test_trading_session_bybit_config.py`,
  - расширен `backend/tests/test_bybit_broker_facade.py` (portfolio shape).

#### DoD (из release map)
- [x] `TradingSession` ветвится по `broker_type` для bybit-конфига.
- [x] Отдельный `ByBitTradingSession` не вводился.

### R6.2 — WS worker ByBit
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R6 → `R6.2`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §9.2
- **Status**: ✅ done

#### Что сделано
- Доработан `backend/app/modules/robots/trading/brokers/bybit.py`:
  - добавлена нормализация crypto-interval (`1m/5m/15m/1h/...`) в формат ByBit WS (`1/5/15/60/...`),
  - WS worker сохраняет актуальный интервал подписки и использует его при `force_resubscribe_websocket`,
  - устранён риск silent fallback на `5` для `15m/1h` из crypto-конфига.
- Добавлен тест:
  - `backend/tests/test_bybit_broker_facade.py::test_bybit_broker_subscribe_prices_uses_crypto_interval`.

#### DoD (из release map)
- [x] ByBit WS path в live worker корректно обрабатывает crypto-интервалы.
- [x] Цены/свечи продолжают поступать через единый Stage2 WS pipeline.

### R6.3 — Execution mapping
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R6 → `R6.3`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §4.3
- **Status**: ✅ done

#### Что сделано
- В `backend/app/modules/bybit/http_client.py` добавлены private-order методы:
  - `create_order(...)`,
  - `cancel_order(...)`,
  - `get_open_orders(...)`.
- В `backend/app/modules/robots/trading/brokers/bybit.py` реализованы:
  - `post_order(...)` (Limit),
  - `post_market_order(...)` (Market),
  - `get_order_state(...)`,
  - `get_orders(...)`,
  - `cancel_order(...)`,
  - маппинг ByBit order status → `EXECUTION_REPORT_STATUS_*` для совместимости с `LiveExecutionService/Stage6Orders`.
- Расширены тесты `backend/tests/test_bybit_broker_facade.py`:
  - покрыт path market/limit/cancel/status/open-orders.

#### DoD (из release map)
- [x] `LiveExecutionService` может работать с ByBit фасадом через единый Stage6 path.
- [x] Market/limit order mapping для bybit покрыт unit-тестом.

### R6.4 — Risk: short, leverage
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R6 → `R6.4`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §5.3
- **Status**: ✅ done

#### Что сделано
- Расширен `backend/app/modules/robots/trading/risk/params.py`:
  - `allow_short: bool`,
  - `max_leverage: float`.
- Обновлён `backend/app/modules/robots/trading/risk/manager.py`:
  - `pre_trade_check` теперь блокирует short при `allow_short=false`,
  - `compute_quantity` ограничивает размер позиции по `max_leverage`.
- Обновлён live risk-gate в `backend/app/modules/robots/trading/stages/stage6_orders.py`:
  - SELL без актива разрешается только при `allow_short=true`,
  - добавлен guard `MAX_LEVERAGE_EXCEEDED` (если задан `free_funds` в risk params).
- Добавлены тесты `backend/tests/test_crypto_risk_extensions.py`:
  - short-block/allow,
  - leverage cap в RiskManager,
  - Stage6 SELL path при `allow_short=true`.

#### DoD (из release map)
- [x] Crypto-risk расширения добавлены в runtime (`allow_short`, `max_leverage`).

### R6.5 — Costs: maker/taker
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R6 → `R6.5`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §5.3
- **Status**: ✅ done

#### Что сделано
- Обновлён `backend/app/modules/robots/trading/costs.py`:
  - `resolve_robot_cost_rates(...)` для `broker_type=bybit` использует `taker_fee_rate` как базовую ставку legacy-path,
  - добавлен `resolve_crypto_fee_rates(...)` для явного maker/taker pair.
- Обновлён live execution path:
  - `backend/app/modules/robots/trading/stages/stage6_orders.py` выбирает комиссию:
    - limit path -> `maker_fee_rate`,
    - market path -> `taker_fee_rate` (через `is_market` API).
- Обновлён session cost context:
  - `backend/app/modules/robots/trading/session.py` теперь прокидывает `maker_fee_rate` и `taker_fee_rate` в `cost_params`.
- Обновлён sim/backtest path:
  - `backend/app/modules/robots/trading/brokers/sim_backtest.py` поддерживает отдельные `maker_fee_rate`/`taker_fee_rate`,
  - `backend/app/modules/robots/trading/runtime/orchestrator.py` передает эти ставки в `SimBacktestBrokerFacade`.
- Добавлены тесты `backend/tests/test_crypto_costs.py`.

#### DoD (из release map)
- [x] maker/taker cost path работает в live + sim.
- [x] Комиссия сохраняется в trade payload/расчетах с crypto-specific ставками.

### R6.6 — Schedule 24/7
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R6 → `R6.6`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §5.3
- **Status**: ✅ done

#### Что сделано
- Обновлён `backend/app/modules/robots/scheduling/schedule_policy.py`:
  - `schedule_type=1` теперь обрабатывается как always-on до проверки weekday/time-window,
  - добавлен fallback: если у робота `broker_type=bybit` и нет явной записи `robot_schedules`, применяется `{"schedule_type": 1}`.
- Добавлены тесты в `backend/tests/test_schedule_policy.py`:
  - `test_schedule_type_1_ignores_weekdays_and_is_always_open`,
  - `test_bybit_without_schedule_defaults_to_always_on`.

#### DoD (из release map)
- [x] `schedule_policy` поддерживает bybit 24/7 режим.
- [x] Для `schedule_type=1` окно всегда открыто.

### R6.7 — `allowed_symbols` в session
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R6 → `R6.7`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §5.4
- **Status**: ✅ done

#### Что сделано
- Обновлён `backend/app/modules/robots/trading/session.py`:
  - добавлен единый guard `_ensure_allowed_instruments_or_raise()` для проверки инструментов после `refresh_config` и перед запуском live-пайплайна,
  - добавлена broker-aware ошибка `_missing_instruments_error()`:
    - для bybit: `WS_4005_ANALOG: ... allowed_symbols empty ...`,
    - для tinvest: сохранено legacy сообщение про `allowed_figis`.
- Обновлён `backend/tests/test_trading_session_bybit_config.py`:
  - добавлен тест `test_trading_session_bybit_empty_symbols_has_ws4005_analog_error`.

#### DoD (из release map)
- [x] В session поддержан `allowed_symbols` refresh path.
- [x] При пустом symbols формируется понятная WS-4005-analog ошибка.

### R6.8 — Live WS `init.broker_type`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R6 → `R6.8`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §7.7.1
- **Status**: ✅ done

#### Что сделано
- Обновлён `backend/app/modules/robots/live_ws.py`:
  - добавлен broker-aware нормализатор `_normalize_instruments(config)`:
    - bybit: `allowed_symbols`/`instruments`,
    - tinvest: `figis`/`allowed_figis`/`strategy_params.figis`,
  - init payload теперь содержит `instruments` + `broker_type`,
  - для backward compatibility сохранено legacy поле `figis` с тем же списком.
- Добавлены тесты `backend/tests/test_live_ws_init_payload.py`:
  - проверка normalize для bybit и tinvest,
  - проверка init payload (`instruments`, `broker_type`, legacy `figis`).
- Обновлён фронт `frontend/src/pages/LivePage.tsx`:
  - чтение WS init теперь `data.instruments ?? data.figis ?? []`.

#### DoD (из release map)
- [x] WS init включает `broker_type`.
- [x] FE получает symbol-friendly список через `instruments` (с fallback на `figis`).

---

## Этап R6 — итог

**Статус этапа:** ✅ завершён (R6.1–R6.8)

**Критерий из release map:** testnet robot — live-цикл с ByBit WS + execution mapping; события в `/ws/live`.

---

## R7 — Crypto backtest и funding

### R7.1 — Orchestrator crypto prefetch
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R7 → `R7.1`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §9.3
- **Status**: ✅ done

#### Что сделано
- Обновлён `backend/app/modules/robots/trading/runtime/orchestrator.py`:
  - `_cache_row_to_candle_dict()` — cache row → T-Invest candle dict,
  - `load_candles_by_symbol_from_cache()` — чтение `candles_cache` (`market=bybit`),
  - `prefetch_crypto_candles_for_replay()` — `ensure_candles_bybit_market` + cache read → `candles_by_symbol`,
  - `build_allowed_symbols_by_date()` — alias для crypto replay.
- Обновлён `backend/app/modules/robots/service.py`:
  - crypto branch в `run_robot_history_backtest()` — prefetch/loading через orchestrator, без MOEX snapshot loop.
- Экспорт `build_allowed_symbols_by_date` в `trading/runtime/__init__.py`.
- Тесты `backend/tests/test_trading_orchestrator.py`:
  - `build_allowed_symbols_by_date`,
  - `prefetch_crypto_candles_for_replay`.

#### DoD (из release map)
- [x] `bybit_market` historical kline → `candles_by_symbol` в replay.

### R7.2 — `bybit_funding_history`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R7 → `R7.2`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §9.3.1.1
- **Status**: ✅ done

#### Что сделано
- Миграция `alembic/versions/0035_bybit_funding_history.py` — таблица `bybit_funding_history`.
- Модель `backend/app/modules/bybit/models.py` — `BybitFundingHistory`.
- `BybitHttpClient.get_funding_history()` — REST `/v5/market/funding/history`.
- `backend/app/modules/robots/trading/data/providers/bybit_market.py`:
  - `fetch_funding_history()`, `ensure_funding_bybit_market()` — upsert + cache-hit skip,
  - `FundingPrefetchStats` в `data/stats.py`.
- `TradingOrchestrator.prefetch_crypto_funding_for_replay()` + вызов из crypto backtest в `service.py`
  (если `costs.funding_rate_enabled` и `instrument_category != spot`).
- Тесты `backend/tests/test_bybit_market_provider.py` — funding upsert + spot skip.

#### DoD (из release map)
- [x] Alembic + model.
- [x] Upsert on backtest start.

### R7.3 — Funding step in backtest session
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R7 → `R7.3`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §9.3.1
- **Status**: ✅ done

#### Что сделано
- `load_funding_history_from_cache()` — чтение `bybit_funding_history` для replay.
- `SimBacktestBrokerFacade.apply_funding_charge()` — debit/credit cash по notional × rate (long pays при rate > 0).
- `BacktestTradingSession`:
  - загрузка funding schedule при старте replay (crypto + `funding_rate_enabled` + category ≠ spot),
  - `_apply_funding_charges_for_bar()` после trading cycle на funding timestamps,
  - dedupe по `(symbol, funding_time)`,
  - crypto backtest: 24/7 bars (без MOEX trading-hours filter).
- Тесты `backend/tests/test_session_backtest_funding.py`.

#### DoD (из release map)
- [x] Charge на funding timestamps в `session_backtest.py`.

### R7.4 — `SimBacktestBrokerFacade` crypto
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R7 → `R7.4`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §4.1
- **Status**: ✅ done

#### Что сделано
- `resolve_robot_cost_rates()` — для `bybit` `ndfl_rate=0` по умолчанию.
- `resolve_backtest_sim_rates()` — единая точка ставок для sim broker (MOEX vs crypto).
- `SimBacktestBrokerFacade`:
  - maker/taker на limit/market с `fee_kind` в trade log,
  - weighted `avg_entry_fee_rate` для round-trip PnL,
  - `_calc_realized_pnl()` без НДФЛ при `ndfl_rate=0`,
  - `fee_totals()` — maker/taker commission + funding.
- `BacktestResult.fee_summary` + `BacktestMetricsCalculator` (`total_funding_val`, `fee_summary`).
- Orchestrator использует `resolve_backtest_sim_rates()`.
- Расширены тесты `backend/tests/test_crypto_costs.py`.

#### DoD (из release map)
- [x] maker/taker; no NDFL для crypto.
- [x] Metrics match fee model.

### R7.5 — `GET /bybit/funding-rate`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R7 → `R7.5`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §7.5
- **Status**: ✅ done

#### Что сделано
- `GET /api/bybit/funding-rate` — read-only текущий funding rate для UI.
- Query: `symbol`, `instrument_category` (`linear`/`inverse`/`spot`), `testnet`.
- `backend/app/modules/bybit/funding.py` — fetch из ByBit `/v5/market/tickers` + in-memory cache (TTL 8h).
- `backend/app/modules/bybit/schemas.py` — `BybitFundingRateResponse`.
- `backend/app/modules/bybit/router.py` + регистрация в `main.py`.
- Auth: `get_current_user` (как остальные read API).
- Spot: `funding_rate=0`, `next_funding_time=null`.
- Тесты `backend/tests/test_bybit_funding_rate.py`.

#### DoD (из release map)
- [x] REST для UI read-only.
- [x] Current rate display (`funding_rate`, `next_funding_time`).

### R7.6 — Backtest UI crypto branch
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R7 → `R7.6`
- **Target ref**: `docs/ROBOTS-ARCHITECTURE-TARGET.md` → §8.4, §8.5
- **Status**: ✅ done

#### Что сделано
- `deriveMarketProfileFromDraft` на `/testing`: MOEX vs crypto UI.
- Брокер **ByBit** в форме; `buildCryptoTradingRobotConfig()` → v3 `type2_bybit` для backtest.
- `TestingCryptoConfigCard`: testnet, category, leverage, maker/taker, funding toggle + preview (`GET /bybit/funding-rate`).
- Crypto universe: фиксированные символы (`allowed_symbols`); скрыты DMS pipeline / MOEX cache / universe DMS.
- `TestingRiskParamsCard`: USDT budget, без НДФЛ/комиссии MOEX (fees в crypto card).
- `TestingBacktestResultPanel`: Symbol column, USDT KPI.
- `bybitService.ts` — клиент funding API.
- `useTestingRobotForm` / `useTestingBacktest` — crypto state + validation symbols.

#### DoD (из release map)
- [x] `/testing` — symbols, fees.
- [x] Run completes with KPI (config path готов для crypto backtest).

---

## Этап R7 — итог

**Статус этапа:** ✅ завершён (R7.1–R7.6)

**Критерий из release map:** crypto backtest на BTCUSDT с funding enabled даёт equity curve.

---

## R8 — UI, ops и config v3 completion

### R8.1 — `deriveMarketProfile` на `/robots`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R8 → `R8.1`
- **Status**: ✅ done

#### Что сделано
- `TradingRobotSettingsPage`: `marketProfile` через `deriveMarketProfileFromDraft`.
- Pipeline visualizer: MOEX P1/P2 только для `marketProfile === 'moex'`; crypto — P3 + risk.
- Условные панели: crypto скрывает MOEX pipeline, показывает crypto config + symbols.
- `buildFullTradingConfig`: ветка `buildCryptoTradingRobotConfig` для crypto.

### R8.2 — `CryptoConfigurator`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R8 → `R8.2`
- **Status**: ✅ done

#### Что сделано
- `frontend/src/modules/robots/components/CryptoConfigurator.tsx` — переиспользуемая форма.
- `TestingCryptoConfigCard` — thin wrapper над `CryptoConfigurator`.
- Settings `/robots` P3: testnet, category, leverage, fees, funding.

### R8.5 — Testnet/Mainnet badge
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R8 → `R8.5`
- **Status**: ✅ done

#### Что сделано
- `resolveBybitEnvironment()` в `resolveProfile.ts`.
- Badge в списке роботов, заголовке settings и Live header (`bybit.testnet`).

### R8.3 — `PortfolioConfigurator`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R8 → `R8.3`
- **Status**: ✅ done

#### Что сделано
- `frontend/src/modules/robots/components/PortfolioConfigurator.tsx` — брокер (tinvest/bybit), ByBit testnet + `account_type`.
- `frontend/src/modules/robots/config/builders/buildPortfolioConfig.ts` — v3 `type1_tinvest` / `type1_bybit`.
- `/robots` type=1: `PortfolioConfigurator` в «Основное», сохранение `config` при create/update.
- Брокер выбирается только при создании (`brokerTypeLocked`).

### R8.4 — `POST /duplicate`
- **Release map ref**: `docs/ROBOTS-ARCHITECTURE-RELEASE_MAP.md` → таблица R8 → `R8.4`
- **Status**: ✅ done

#### Что сделано
- `POST /api/robots/duplicate` — копия робота со `status=inactive`.
- `backend/app/modules/robots/config/duplicate.py` — merge config, reset universe, broker migration.
- Копируются: `signal_generation`, `risk`, `costs`, `schedule`; сброс: universe, `allowed_figis`/`allowed_symbols`, `candidate_pool`.
- UI: кнопка «Дублировать робота» + wizard смены брокера (MOEX ↔ crypto).
- Тесты: `backend/tests/test_robot_duplicate.py`.

### R8.6 — v2 deprecation (UI writes v3 only)
- **Status**: ✅ done

#### Что сделано
- `buildTradingRobotConfig` → `buildMoexConfig` (MOEX) / `buildCryptoTradingRobotConfig` (ByBit).
- `buildTradingRobotConfigV2` помечен deprecated (только sandbox fallback).
- Backend `validate_robot_config` для type2_tinvest: `migrate_v2_to_v3` перед валидацией.
- `Type2TinvestConfig`: `config_version: 3`, `schema_profile`, `instrument_id_type`.

### R8.7 — OpenAPI oneOf profiles
- **Status**: ✅ done

#### Что сделано
- `RobotConfigProfile` discriminated union в `schemas.py` (`schema_profile`).
- `RobotValidateConfigResponse.normalized_config` — typed oneOf.
- Тесты: `backend/tests/test_openapi_robot_config.py`.
- Frontend `types/profiles.ts` — все четыре профиля.

### R8.8 — Документация as-is
- **Status**: ✅ done

#### Что сделано
- `docs/ROBOTS-TECH-PORTFOLIO-TRADING.md` §30 — config v3, UI profiles, duplicate, crypto.

**Статус этапа R8**: ✅ complete (R8.1–R8.8)

---

## Сводка R0–R8

| Release | Статус |
|---------|--------|
| R0 BRD-ARCH-04 | ✅ |
| R1 MOEX hardening | ✅ |
| R2 Config v3 MOEX | ✅ |
| R3 Cache schema | ✅ |
| R4 ByBit foundation | ✅ |
| R5 Crypto universe + portfolio | ✅ |
| R6 Crypto live | ✅ |
| R7 Crypto backtest + funding | ✅ |
| R8 UI + ops | ✅ |

**Хвосты вне release map:** E2E testnet smoke на prod, live funding accrual, `bybit_accounts` table, `openapi-typescript`.
