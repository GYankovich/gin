# MOC — бэктест и соседние домены (GIN)

Карта содержимого для Obsidian: функциональные блоки и пути от корня репозитория.

Теги: `#gin` `#backtest` `#testing` `#robots`

---

## Документация и спеки

- [[TESTING-BACKTEST-REFERENCE]] — `docs/TESTING-BACKTEST-REFERENCE.md` (as-built справочник: `/testing`, history-backtest, компоненты и потоки данных)
- [[TESTING-UI-RELEASE_MAP]] — `docs/TESTING-UI-RELEASE_MAP.md` (release map: унификация UI `/testing`, T0–T6)
- [[TESTING-UI-RELEASE_STATUS]] — `docs/TESTING-UI-RELEASE_STATUS.md` (статус T0–T6, DoD по подзадачам)
- [[TESTING-UI-ACCEPTANCE-CHECKLIST]] — `docs/TESTING-UI-ACCEPTANCE-CHECKLIST.md` (приёмочный чеклист T0–T6, E2E smoke)
- [[TESTING-UI-BACKEND-CHANGES]] — `docs/TESTING-UI-BACKEND-CHANGES.md` (спека backend: crypto auto-screening, history filter)
- [[BRD-ARCH-04-trading-core-facade-orchestrator]] — `docs/BRD-ARCH-04-trading-core-facade-orchestrator.md` (ядро + фасад + execution, live/backtest)
- [[BRD-ARCH-03-unified-engine-architecture]] — `docs/BRD-ARCH-03-unified-engine-architecture.md`
- [[BRD-ARCH-02-unified-backtest-testing-spec]] — `docs/BRD-ARCH-02-unified-backtest-testing-spec.md`
- [[BRD-01-backtest-robot-dynamic-universe-presets]] — `docs/BRD-01-backtest-robot-dynamic-universe-presets.md`
- [[ARCH-01-unified-moex-candles-backtest]] — `docs/ARCH-01-unified-moex-candles-backtest.md`
- [[TESTING-UX-REFACTOR-SPEC]] — `docs/ui/TESTING-UX-REFACTOR-SPEC.md`
- [[OBSIDIAN_SOURCE_SCANNER_SETUP]] — `docs/OBSIDIAN_SOURCE_SCANNER_SETUP.md`

> Если вики-ссылки не резолвятся, откройте файл по пути в бэктиках или настройте путь в vault.

---

## Тестирование (UI `/testing`)

Страница и сборка:

- `frontend/src/pages/TestingPage.tsx`
- `frontend/src/app/App.tsx` — роут `testing`
- `frontend/src/pages/testing/TestingPageContent.tsx`
- `frontend/src/pages/testing/TestingPageSkeleton.tsx`
- `frontend/src/pages/testing/hooks/useTestingPage.ts`

Бэктест в UI:

- `frontend/src/pages/testing/TestingBacktestRunSection.tsx`
- `frontend/src/pages/testing/TestingBacktestHistoryCard.tsx`
- `frontend/src/pages/testing/TestingBacktestResultPanel.tsx`
- `frontend/src/pages/testing/TestingBacktestEquityChart.tsx`
- `frontend/src/pages/testing/hooks/useTestingBacktest.ts`

Пайплайн, MOEX-кеш, риск, робот:

- `frontend/src/pages/testing/TestingPipelineCard.tsx`
- `frontend/src/pages/testing/testingPipeline.ts`
- `frontend/src/pages/testing/testingUtils.ts`
- `frontend/src/pages/testing/TestingMoexCacheCard.tsx`
- `frontend/src/pages/testing/hooks/useMoexCandleJobState.ts`
- `frontend/src/pages/testing/TestingRiskParamsCard.tsx`
- `frontend/src/pages/testing/TestingRobotParamsCard.tsx`
- `frontend/src/pages/testing/hooks/useTestingRobotForm.ts`
- `frontend/src/pages/testing/grainSeedPresets.ts`
- `frontend/src/pages/testing/TestingSectionState.tsx`

API с фронта:

- `frontend/src/services/robotService.ts`
- `frontend/src/services/marketService.ts`
- `frontend/src/types/robot.ts`

---

## HTTP API бэктеста (роботы)

- `backend/app/modules/robots/router.py` — `history-backtest`, runs, cancel, list, compare
- `backend/app/modules/robots/service.py`
- `backend/app/modules/robots/usecases.py` — в т.ч. `robot_backtest_usecase`
- `backend/app/modules/robots/schemas.py`
- `backend/app/modules/robots/models.py`
- `backend/app/modules/robots/queries.py`

---

## Движок бэктеста (симуляция)

- `backend/app/modules/robots/trading/backtest/__init__.py`
- `backend/app/modules/robots/trading/backtest/engine.py`
- `backend/app/modules/robots/trading/backtest/sim_executor.py`
- `backend/app/modules/robots/trading/backtest/broker_emulator.py`
- `backend/app/modules/robots/trading/backtest/virtual_portfolio.py`
- `backend/app/modules/robots/trading/backtest/metrics.py`
- `backend/app/modules/robots/trading/backtest/persistence.py`
- `backend/app/modules/robots/trading/backtest/dms_emulator.py`

---

## Стратегии и сигналы (используются в бэктесте)

- `backend/app/modules/robots/trading/strategies/__init__.py`
- `backend/app/modules/robots/trading/strategies/base.py`
- `backend/app/modules/robots/trading/strategies/grain_seed.py`
- `backend/app/modules/robots/trading/grain_seed_orchestrator.py`
- `backend/app/modules/robots/trading/indicators/service.py`
- `backend/app/modules/robots/trading/indicators/__init__.py`
- `backend/app/modules/robots/trading/costs.py`
- `backend/app/modules/robots/trading/cache.py`
- `backend/app/modules/robots/trading/instrument_selector.py`

---

## DMS (отбор вселенной / превью пайплайна)

- `backend/app/modules/dms/router.py`
- `backend/app/modules/dms/service.py`
- `backend/app/modules/dms/schemas.py`
- `backend/app/modules/dms/models.py`
- `backend/app/modules/dms/scheduler.py`

---

## Рыночные данные и кеш свечей

- `backend/app/modules/market_data_v1/router.py`
- `backend/app/modules/market_data_v1/service.py`
- `backend/app/modules/market_data_v1/repository.py`
- `backend/app/modules/market_data_v1/scheduler.py`
- `backend/app/modules/market_data_v1/moex_fetch.py`
- `backend/app/modules/market_data_v1/schemas.py`
- `backend/app/modules/market_data/router.py`
- `backend/app/modules/market_data/service.py`
- `backend/app/modules/market_data/repository.py`
- `backend/app/modules/moex/http_gate.py`
- `backend/app/modules/moex/securities_listing_archive.py`

Корпоративные действия (дивиденды / equity-сценарии):

- `backend/app/modules/corporate_actions/dividend_calendar_service.py`
- `backend/app/modules/corporate_actions/etl.py`
- `backend/app/modules/corporate_actions/scheduler.py`

---

## Трейдинг (live, тот же модуль `robots`)

- `backend/app/modules/robots/trading/scheduler.py`
- `backend/app/modules/robots/trading/robot.py`
- `backend/app/modules/robots/trading/session.py`
- `backend/app/modules/robots/trading/stages/stage1_collect.py` … `stage6_orders.py`
- `backend/app/modules/robots/trading/brokers/` — `factory.py`, `tinvest.py`, `base.py`, и др.
- `backend/app/modules/robots/live_hub.py`
- `backend/app/modules/robots/live_ws.py`
- `frontend/src/pages/RobotsPage.tsx`
- `frontend/src/pages/TradingRobotSettingsPage.tsx`

---

## Обновление портфеля

- `backend/app/modules/robots/portfolio_updater/__init__.py`
- `backend/app/modules/robots/portfolio_updater/scheduler.py`
- `backend/app/modules/robots/portfolio_updater/robot.py`
- `backend/app/modules/robots/portfolio_updater/queries.py`
- `backend/app/modules/robots/scheduler.py`

---

## Миграции БД (бэктест / свечи)

- `alembic/versions/0020_market_backtests.py`
- `alembic/versions/0027_backtest_storage_tables.py`
- `alembic/versions/0028_backtest_schema_v1.py`
- `alembic/versions/0029_shared_moex_candles.py`
- `alembic/versions/0030_equity_div_tqbr_bt.py` — при наличии в ветке

---

## Автотесты

- `backend/tests/test_backtest_strategies.py`

---

## Cursor skills (шаблоны)

- `.cursor/skills/backtest-requirements-template/SKILL.md`
- `.cursor/skills/backtest-vectorized-template/SKILL.md`
- `.cursor/skills/backtest-event-driven-template/SKILL.md`
- `.cursor/skills/trading-metrics-calculation/SKILL.md`

---

## Scanner-output (если vault = весь репозиторий)

- `scanner-output/Graph/MOC EPIC — backend — EPIC Backtesting.md`
- `scanner-output/Graph/MOC EPIC — frontend-tsx — EPIC Backtesting.md`

Пример встраивания в заметку Obsidian: `![[scanner-output/Graph/MOC EPIC — backend — EPIC Backtesting]]` (если файл доступен как заметка).

---

## Сводка

Ядро бэктеста в коде: `backend/app/modules/robots/trading/backtest/` + `robots/router|service|schemas` + `frontend/src/pages/testing/*` + документы в `docs/` с `backtest` / `testing` в имени + миграции `0020`, `0027`, `0028` (и связанные `0029`, `0030`).
