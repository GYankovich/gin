# Техническая документация: роботы обновления портфеля и торговый

## 1. Область документа

Документ описывает текущую реализацию двух подсистем в backend:

- **Робот обновления портфеля** (`type=1`, `portfolio_updater`)
- **Торговый робот** (`type=2`, `trading`, live и backtest-контуры)

Цель: дать единую техническую точку входа по архитектуре, жизненному циклу, конфигурации, расписанию, API, хранению данных и отказоустойчивости.

---

## 2. Точки входа и запуск

### 2.1 Startup/shutdown приложения

В `backend/app/main.py` на старте FastAPI:

- запускается `start_portfolio_scheduler()`
- запускается `start_trading_scheduler()`

На остановке:

- вызываются `stop_portfolio_scheduler()`
- вызываются `stop_trading_scheduler()`
- закрываются активные websocket-сессии через `global_websocket_manager.shutdown_all()`

### 2.2 Роутинг

HTTP API роботов подключается через:

- `backend/app/modules/robots/router.py`
- префикс: `/api/robots` (роутер модуля `robots`)

Есть также служебные force-run endpoint'ы:

- `GET /api/scheduler/portfolio/run`
- `GET /api/scheduler/trading/run/{robot_id}`

---

## 3. Архитектурная карта модулей

## 3.1 Portfolio updater

- Планировщик: `backend/app/modules/robots/portfolio_updater/scheduler.py`
- Исполнитель: `backend/app/modules/robots/portfolio_updater/robot.py`
- SQL для выборки активных роботов: `backend/app/modules/robots/portfolio_updater/queries.py`

## 3.2 Trading

- Планировщик live-сессий: `backend/app/modules/robots/trading/scheduler.py`
- Фабрика сессий: `backend/app/modules/robots/trading/session_factory.py`
- Live-сессия: `backend/app/modules/robots/trading/session.py`
- Backtest-сессия: `backend/app/modules/robots/trading/session_backtest.py`
- Legacy/modular bot pipeline: `backend/app/modules/robots/trading/robot.py`
- Единый pipeline-фильтр тикеров: `backend/app/modules/robots/trading/pipeline/runner.py`
- Политика расписаний: `backend/app/modules/robots/scheduling/schedule_policy.py`

---

## 4. Робот обновления портфеля (PortfolioUpdaterRobot)

## 4.1 Назначение

`PortfolioUpdaterRobot` синхронизирует пользовательские данные с брокером:

- получает список счетов
- получает портфель по каждому счету
- сохраняет snapshot портфеля в БД
- обновляет timestamp синхронизации счета
- при необходимости синхронизирует операции счета
- при вызове из trading-сессии может обновлять `daily_universe` из текущих позиций

## 4.2 Источники данных

Через `TInvestFacade` и `TInvestService`:

- `GetAccounts`
- `GetPortfolio`
- синхронизация операций аккаунта

Все вызовы логируются в БД API-логов робота (через `log_api_call` в базовом роботе).

## 4.3 Режимы вызова

`execute(..., **kwargs)` поддерживает режимы:

- `caller="scheduler"` (по умолчанию):
  - `sync_operations=True` (синхронизация операций включена)
- `caller="trading_robot"`:
  - `write_daily_universe=True`
  - `sync_operations=False` (быстрый режим внутри trading-сессии)

## 4.4 Результат выполнения

Возвращается агрегированный ответ:

- `status`
- `accounts_found`
- `portfolios_updated`
- `snapshots_saved`
- `execution_time_ms`

## 4.5 Планировщик обновления портфеля

`PortfolioUpdaterScheduler`:

- интервал цикла: `60` секунд
- каждый цикл:
  - выбирает активных роботов `type=1`
  - вызывает `PortfolioUpdaterRobot.run(...)` для каждого
  - пишет агрегированную статистику цикла в логи
- корректно закрывает DB-сессию и обрабатывает rollback при ошибке

---

## 5. Торговый контур (Trading)

## 5.1 Общая модель

Торговля реализована через объект **сессии** на робота:

- `TradingScheduler` выбирает роботов `type=2`
- проверяет, можно ли запускать сессию по расписанию
- создает задачу `asyncio.Task` для каждого робота
- task выполняет `session.run()`

Сессия совмещает:

- поток рыночных событий (WebSocket, очереди)
- торговый цикл (портфель, позиции, сигналы, заявки, статусы)

## 5.2 Планировщик торговых сессий

`TradingScheduler`:

- проверка активных роботов каждые `30` секунд
- использует `build_collect_scheduled_trading_robots_query()`
- не запускает вторую сессию, если текущая для робота еще активна
- ведет `active_sessions: Dict[int, asyncio.Task]`
- при остановке:
  - отменяет активные task'и
  - ожидает их завершения (`gather`)
  - гасит глобальные websocket-подключения

## 5.3 Политика расписания

`should_start_trading_session(robot)` в `schedule_policy.py`:

- поддержка `robot_schedules` и fallback на `config.risk.*`
- `weekdays` — битовая маска (1=пн ... 32=вс)
- временные окна интерпретируются в MSK
- `schedule_type`:
  - `1` — always
  - `2` — custom time window
  - `3` — market window (дефолт 10:00-18:45)

---

## 6. TradingSession: жизненный цикл live-сессии

## 6.1 Инициализация

При создании `TradingSession`:

- может открыть собственную DB-сессию (`db=None` -> `SessionLocal()`)
- настраивает внутренние очереди:
  - `price_queue`
  - `order_queue`
  - `signal_queue`
- загружает config (account, figi, strategy, risk, broker, update interval)
- нормализует издержки:
  - `broker_commission_rate`
  - `ndfl_rate`

## 6.2 Run-последовательность (high-level)

`session.run()`:

1. Создает execution log в БД
2. Гарантирует `account_id` (автовыбор счета, если не задан)
3. Вызывает встроенный sync через `PortfolioUpdaterRobot` (быстрый режим)
4. Обновляет позиции аккаунта (для ограничений, например short-sell checks)
5. Регистрирует робота в `indicator_service` и делает bootstrap свечей
6. Запускает параллельно:
   - `_websocket_worker()`
   - `_trading_worker()`
7. На завершении:
   - unregister индикаторов
   - закрытие broker facade
   - завершение execution log

## 6.3 WebSocket worker

`_websocket_worker()`:

- подключается к broker websocket через `Stage2WebSocket`
- подписывает FIGI + candle interval
- читает events (price / candle_closed)
- обновляет `cached_prices` и кладет события в `price_queue`
- при отсутствии событий выполняет принудительную переподписку
- при ошибках делает reconnect-loop

## 6.4 Trading worker

`_trading_worker()`:

- выполняет циклы торговли до остановки сессии
- каждый цикл делегирует логику в `trading.core.trading_core.run_single_trading_cycle`
- завершает цикл с фиксацией статуса и контекста API-вызовов
- при ошибках:
  - rollback
  - статус цикла `failed`
  - backoff sleep

## 6.5 Основные этапы торгового цикла

Внутри сессии используется staging-пайплайн:

- `Stage3Portfolio` — состояние портфеля и free funds
- `Stage4Positions` — открытые позиции, stop-loss/take-profit, закрытия
- `Stage5Signals` — генерация сигналов по стратегии
- Execution service — отправка ордеров, маппинг статусов, polling заявок

Отдельно поддерживаются правила для `grain_seed`:

- orchestration-ограничения
- force close по времени
- сверка и отмена открытых заявок

---

## 7. Backtest-контур

## 7.1 BacktestTradingSession

`BacktestTradingSession` наследует `TradingSession`, но:

- использует `SimBacktestBrokerFacade`
- отключает live side-effects:
  - без live events
  - без записи execution log/cycles/api logs в DB-таблицы live-логов
- исполняет replay исторических баров через `_feed_bar` и `_run_single_trading_cycle`
- собирает:
  - `equity_curve`
  - `signals`
  - `trade_log`
  - drawdown и return metrics

## 7.2 Оркестрация backtest

`run_session_history_backtest(...)` в `session_backtest.py` сейчас проксирует в:

- `trading/runtime/orchestrator.py`
- метод `TradingOrchestrator.run_backtest_replay(...)`

Это целевой production-путь; старый `engines/unified_runner.py` помечен как deprecated.

---

## 8. PipelineRunner и селекция universe

`PipelineRunner` — единый слой фильтрации тикеров:

- применяет pipeline-фильтры через `DmsService._evaluate_pipeline_row`
- поддерживает режимы логики `ALL`/`ANY`
- может добавлять фильтр дивидендного календаря
- возвращает детализированные решения:
  - accepted
  - rejected (+ reason)
  - decisions с payload по стадиям

Используется как часть унифицированного подхода к отбору инструментов для trading/backtest.

---

## 9. API: ключевые endpoint'ы по роботам

Базовый префикс: `/api/robots`

## 9.1 Управление роботами

- `POST /data` — список роботов пользователя
- `POST /create` — создать робота (`type=1|2`)
- `GET /id/{robot_id}` — получить робота
- `POST /update` — patch обновление
- `POST /change_status` — включить/выключить
- `POST /delete` — мягкое удаление
- `POST /config` — обновить config
- `POST /schedule` — обновить расписание (`robot_schedules`)

## 9.2 Trading strategy/meta

- `GET /strategies`
- `GET /strategies/{name}`
- `GET /trading-defaults`

## 9.3 Backtest

- `POST /history-backtest` (sync или `202 Accepted` с фоновой задачей)
- `GET /history-backtest/runs/active`
- `GET /history-backtest/runs/{run_id}`
- `GET /history-backtest/runs/{run_id}/status`
- `POST /history-backtest/runs/{run_id}/cancel`
- `POST /history-backtest/list`
- `POST /history-backtest/run`
- `POST /history-backtest/compare`
- `POST /history-backtest/compare/list`
- `POST /history-backtest/compare/id`

## 9.4 Live/Universe jobs

- `POST /live/snapshot`
- `POST /migrate-config-v2`
- `POST /jobs/historical-screening`
- `POST /jobs/paper-selection`
- `POST /sync-universe`
- `POST /instruments/auto-select`

---

## 10. Основные данные и таблицы (по коду модуля robots)

В SQL-запросах и сервисах используются (минимально):

- `robots`
- `api_tokens`
- `robot_schedules`
- `robot_execution_logs`
- `robot_logs`
- `robot_signals`
- `robot_trades`
- `backtest_runs`
- `daily_universe`

Примечания:

- Для портфеля/операций используются также таблицы tinvest-модуля (через `TInvestService`).
- Для истории backtest и сравнений используются специализированные backtest-таблицы (через `robot_service`).

---

## 11. Логирование и наблюдаемость

## 11.1 Уровни логирования

- системные логгеры:
  - `robots.portfolio.scheduler`
  - `robots.trading.scheduler`
  - `robots.trading.session`
- execution/API логи в БД для запуска и вызовов
- событийные live-публикации через `live_event_hub` (для UI/WS)

## 11.2 Что особенно важно мониторить

- доля ошибок reconnect в websocket worker
- длительность сессий и циклов
- количество `skipped/failed` сигналов/сделок
- рост очередей `price_queue` и `order_queue`
- корректность закрытия task'ов на shutdown

---

## 12. Отказоустойчивость и обработка ошибок

- в обоих шедулерах есть retry-loop с backoff
- DB ошибки в цикле сопровождаются rollback
- при проблемах connectivity вызывается `try_dispose_pool_on_connectivity_error`
- отмены сессий и shutdown обрабатывают `asyncio.CancelledError`
- в history-backtest async-продолжение переводит run в `FAILED` при исключении

---

## 13. Конфигурация робота (практические поля)

Критичные поля `robots.config` для `type=2`:

- `account_id`
- `allowed_figis`
- `strategy`
- `strategy_params`
- `risk`
- `broker_type`
- `update_interval_seconds`
- (опционально) параметры universe/pipeline v2

Критичные поля расписания:

- `robot_schedules.schedule_type`
- `robot_schedules.interval_seconds`
- `robot_schedules.start_time`
- `robot_schedules.end_time`
- `robot_schedules.weekdays`

---

## 14. Операционные сценарии

## 14.1 Нормальный live-сценарий

1. Приложение стартует и поднимает оба шедулера.
2. Portfolio scheduler обновляет snapshot'ы по активным `type=1`.
3. Trading scheduler поднимает live-сессии по `type=2` в окне расписания.
4. Сессия:
   - синхронизирует портфель
   - запускает WS поток
   - циклически торгует и пишет логи/события

## 14.2 Исторический backtest

1. Клиент вызывает `/api/robots/history-backtest`.
2. Создается run (возможно async через `202`).
3. Выполняется replay-симуляция через orchestrator/backtest session.
4. Статус и результаты запрашиваются через `/history-backtest/runs/*`.

---

## 15. Расширение и точки модификации

- Новый брокер:
  - добавить facade в `trading/brokers/*`
  - подключить в `create_broker_facade`/normalization
- Новая стратегия:
  - добавить стратегию в `trading/strategies/*`
  - зарегистрировать в strategy metadata/API
- Новые риск-ограничения:
  - `trading/risk/*` + интеграция в cycle
- Новые фильтры universe:
  - расширить PipelineRunner и/или DMS pipeline evaluator

---

## 16. Ограничения и технический долг (по текущему состоянию)

- В кодовой базе присутствуют параллельные ветки эволюции trading (legacy и unified), что усложняет онбординг.
- Часть старых модулей помечена как deprecated, но еще остается рядом с production-путем.
- Много логики завязано на rich config JSON, где важна строгая валидация схемы при изменениях.

---

## 17. Быстрый чеклист перед прод-изменениями

- Проверить, что `start/stop` шедулеров не ломается на lifespan.
- Проверить, что нет дублей live-сессий для одного `robot_id`.
- Проверить rollback/commit в новых местах DB IO.
- Проверить корректность timezone (MSK/UTC) в расписании.
- Проверить обратную совместимость `config` (особенно для type=2).
- Для backtest: проверить cancel/progress и финальный статус run.

---

## 18. Связь с UI: где лежат поля

Ниже — практический mapping полей формы `frontend/src/pages/TradingRobotSettingsPage.tsx` к payload/config на backend.

## 18.1 Общие поля робота

- UI `Название робота` -> `POST /robots/create` поле `name`
- UI `Токен` -> `token_id`
- UI `Тип робота` -> `type` (1/2)
- UI `Цикл робота (мин)` -> в schedule patch: `poll_interval_hours` (минуты переводятся в часы)
- UI `Часы работы` -> schedule patch: `trading_hours_start`, `trading_hours_end`
- UI `Дни недели` -> schedule patch: `allowed_weekdays` (битовая маска)

## 18.2 Торговая логика (П3)

Основной config (`POST /robots/config`) содержит:

- `strategy` (например `grain_seed`, `momentum_breakout`, `reversion_to_ma`)
- `strategy_params` (параметры стратегии + `interval` + `initial_capital`)
- `risk`:
  - `stop_loss_percent`
  - `take_profit_percent`
  - `max_position_percent`
  - `max_position_rub`
  - `max_daily_loss`
  - `trading_hours_start`, `trading_hours_end`, `allowed_weekdays`
- `costs`:
  - `broker_commission_rate`
  - `ndfl_rate`

## 18.3 Universe и pipeline (П1/П2)

UI режимы:

- `fixed`
- `tqbr_scan`
- `dms_pipeline`

Пишутся в:

- `universe_mode`
- `fixed_tickers`
- `universe_refresh_minutes` (legacy)
- `pipeline.mode` + `pipeline.filters` (legacy)
- и в v2-блоки:
  - `historical_screening.*`
  - `paper_selection.*`
  - `signal_generation.*`

## 18.4 Поля П1 из UI

- UI `Интервал свечей MOEX` -> `historical_screening.interval`
- UI `Глубина (дней)` -> `historical_screening.lookback_days`
- UI `Пересчёт (MSK)` -> `historical_screening.refresh.daily_at_msk`
- UI исторические фильтры -> `historical_screening.filters`

## 18.5 Поля П2 из UI

- UI `Режим фильтров` -> `paper_selection.mode` (`ALL`/`ANY`)
- UI `Пересчёт отбора (мин, в сессии)` -> `paper_selection.refresh.every_minutes`
- UI фильтры snapshot -> `paper_selection.filters`
- результат П2 на backend -> `allowed_figis` и записи в `daily_universe`

---

## 19. Pipeline-стадии П1/П2/П3 в backend-терминах

## 19.1 П1: Historical screening

Компонент: `backend/app/modules/robots/universe_jobs.py::rebuild_candidate_pool`

Что делает:

1. Читает `historical_screening` из `config` (через v2 migration helper).
2. Выбирает universe-кандидатов (`tqbr_securities` / fixed list).
3. Прогревает свечи MOEX через market data facade (`ensure_candles`).
4. Применяет historical-фильтры (в первую очередь ATR) с использованием `candles_cache`.
5. Сохраняет `config.candidate_pool` (+ `as_of`, stats).
6. Обновляет `config.universe_jobs_state.last_historical_screening_at`.

Результат П1: `candidate_pool.tickers`.

## 19.2 П2: Paper selection

Компонент: `backend/app/modules/robots/universe_jobs.py::rebuild_paper_selection`

Что делает:

1. Берет вход `paper_selection.input`:
   - `candidate_pool`, либо
   - `tqbr_all`, либо
   - `fixed`.
2. Вызывает `robot_service.sync_live_universe_from_pipeline(...)`.
3. На стороне DMS/pipeline пересчитывает daily universe.
4. Обновляет `allowed_figis` в конфиге робота.
5. Обновляет `config.universe_jobs_state.last_paper_selection_at`.

Результат П2: `allowed_figis` + диагностические данные (accepted/rejected, snapshot_id).

## 19.3 П3: Signal generation + execution

Компонент: `backend/app/modules/robots/trading/session.py`

Что делает:

1. Поднимает websocket/market stream.
2. Обновляет портфель и позиции.
3. Генерирует сигналы (`Stage5Signals`) по `strategy/strategy_params`.
4. Прогоняет риск-правила (`risk`, cost rates, strategy-specific orchestration).
5. Выставляет ордера через execution service.
6. Сохраняет/обновляет `robot_signals`, `robot_trades`, execution/api logs.

Результат П3: поток торговых решений и исполнений в live-сессии.

---

## 20. API валидации: что делает кнопка «Проверить»

На UI это не только локальная проверка формы.

## 20.1 Локальная валидация (frontend)

`collectRobotSettingsIssues(...)` и `validateRobotSettings(...)` проверяют:

- обязательные поля (`name`, `token`, fixed tickers в fixed-режиме)
- корректность окна часов
- согласованность цикла и стратегии
- базовые риск-проверки (капитал, stop/take, лимиты позиции)

При наличии `severity=error` запуск блокируется (`lastCheckOk=false`).

## 20.2 Серверная preview-проверка П2

Для торгового робота (`type=2`) и не-fixed universe кнопка также вызывает:

- `POST /dms/pipeline/preview`

С этим payload:

- `robot_id`
- `board`
- `filters`
- `mode`

Если preview не проходит, UI получает blocking issue:

- `field=pipeline`
- сообщение: "Не удалось выполнить тест фильтров П2 (preview)"

Итог кнопки `Проверить`:

- валидирует форму + пробует preview pipeline
- выставляет `lastCheckOk`
- только при `lastCheckOk=true` UI разрешает `Запустить`

---

## 21. Событийная модель: что фронтенд получает по WebSocket

Endpoint:

- `GET/WS /ws/live?robot_id=...&token=...`

## 21.1 Типы сообщений

Со стороны backend (`live_ws.py` + `live_event_hub`) в UI уходят:

- `init` — стартовый пакет с `figis`, `robot_id`, `broker_type`
- `price` — рыночная цена (`figi`, `price`, `time`)
- `log` — текстовые сообщения сессии/подписок
- `order` — изменения статусов ордеров/исполнений
- `ping` — heartbeat при простое
- `error` — фатальная ошибка (auth, robot not found, empty instruments, broker ws)

## 21.2 Общие envelope-поля

Writer в `live_ws.py` дополняет payload:

- `event_id` (монотонный seq)
- `run_id` (если есть контекст запуска)
- `cycle_id` (если есть контекст цикла)
- `decision_id` (если есть идентификатор решения)

## 21.3 Подписки из UI

UI может отправлять команды:

- `{ action: "subscribe", figi | figis[] }`
- `{ action: "unsubscribe", figi | figis[] }`

Backend динамически меняет набор подписок брокерского стрима.

---

## 22. Dead-letter и обработка неуспешных сообщений

На текущий момент отдельной DLQ-таблицы/шины для robots/DMS **нет**.

Фактическая модель "dead-letter-like" (best effort):

- DMS snapshot ошибки фиксируются в `market_snapshot.status='ERROR'` + `error_message`.
- DMS queue processing возвращает `errors[]` в `process_pending_subscriptions`.
- История и архив snapshot'ов переносятся в history-таблицы через cleanup.
- В trading:
  - ошибки цикла/сессии помечаются в execution logs (`failed/partial`)
  - rejected/failed ордера отражаются в статусах trade/order events.
- В backtest run:
  - при исключении run переводится в `FAILED` с `error_message`.

Рекомендация для развития:

- выделить отдельную DLQ сущность (например `robot_dead_letters`) с полями:
  - `source`, `robot_id`, `run_id`, `payload`, `error`, `attempts`, `next_retry_at`, `status`
- добавить ручной replay endpoint для операторов.

---

## 23. Метрики и мониторинг (текущий слой)

## 23.1 Что уже есть из коробки

Через логи и API-ответы доступны:

- Portfolio scheduler:
  - `total/processed/skipped/errors`
  - `accounts_found`, `snapshots_saved`
- Trading session:
  - `prices_received`, `signals_generated`, `orders_placed`, `errors`
  - API call counters по категориям (portfolio/orders/stream/candles)
- Backtest:
  - `progress_percent`, `eta_seconds`, `run_phase`
  - финальные KPI (`total_return_percent`, `max_drawdown_percent`)
- Universe jobs:
  - П1: `passed/scanned`, cache/fetch stats в candidate_pool stats
  - П2: `allowed_figis`, `candidate_pool_size`, `snapshot_id`, `recomputed`
- DMS:
  - queue processing summary (`processed_subscriptions`, `created_snapshots`, `analyzer_written_rows`, `errors`)
  - cleanup summary (`deleted_snapshots`, `moved_rows`)

## 23.2 Минимальный дашборд мониторинга (рекомендуемый)

- Ошибки:
  - доля `status=ERROR` по snapshot
  - доля failed trading cycles / sessions
- Производительность:
  - p95 времени цикла trading session
  - p95 `process_pending_subscriptions`
- Данные:
  - размер `allowed_figis` и `candidate_pool` по роботам
  - stale-возраст `last_historical_screening_at` и `last_paper_selection_at`
- Поток:
  - reconnect count websocket
  - queue lag по `price_queue`/`order_queue`

---

## 24. Кэш и поля UI «Интервал свечей MOEX» / «Пересчёт (MSK)»

## 24.1 Где именно используется кэш свечей

Для П1 ATR-скрининга используется `candles_cache` (через DMS service):

- `dms_service._ensure_candles_cached_for_tickers(...)`
- `dms_service._upsert_candles_cache(...)`

Поведение:

- если диапазон свечей уже покрыт -> `cache_full_hits`
- если есть "дыры" диапазона -> дозагрузка только недостающих интервалов
- для intraday может обновляться последний день (`refresh_recent_intraday`)

## 24.2 Как UI-поля влияют на кэш

- `Интервал свечей MOEX` (`historical_screening.interval`):
  - задает таймфрейм исторических свечей для П1
  - влияет на ключ/срез данных в `candles_cache`
- `Глубина (дней)` (`historical_screening.lookback_days`):
  - задает требуемый исторический диапазон
  - влияет, сколько данных должно быть в кэше
- `Пересчёт (MSK)` (`historical_screening.refresh.daily_at_msk`):
  - задает момент daily запуска П1
  - при запуске П1 кэш переиспользуется и/или догружается

## 24.3 Кэш snapshot (П2)

П2 опирается на market snapshot:

- создается в DMS (`create_snapshot`) с `ttl_minutes`
- может переиспользоваться актуальный snapshot
- при `force_refresh_snapshot=true` создается новый

Это отдельный слой кэша/материализации относительно `candles_cache`.

## 24.4 Практический эффект для UI

- При стабильном universe и тех же фильтрах кнопка `Проверить` (preview П2) обычно отрабатывает быстрее благодаря прогретым snapshot/candles данным.
- Изменение `Интервал свечей MOEX` часто приводит к догрузке свечей при первом запуске П1 на новом интервале.
- Ежедневный `Пересчёт (MSK)` обновляет candidate pool, но не обязательно вызывает полный refetch, если кэш покрывает диапазон.

---

## 25. Rate limiting и ограничения API

## 25.1 Где есть внешние лимиты

Система активно ходит во внешние контуры:

- брокерские API (T-Invest/T-Bank): accounts, portfolio, orders, market stream, candles
- MOEX/ISS-источники (через DMS/market data)

Оба контура имеют ограничения по частоте запросов и burst-нагрузке.

## 25.2 Как это реализовано в текущем коде

В контуре robots/trading используется брокерский фасад и вспомогательные компоненты:

- `backend/app/modules/robots/trading/brokers/*`
- `backend/app/modules/robots/trading/brokers/rate_limiter.py`
- `backend/app/modules/robots/trading/brokers/global_websocket.py`

Фактическая стратегия защиты от лимитов:

- повторное использование websocket-подключений (уменьшение REST polling)
- батч-подписки/переподписки вместо множества одиночных вызовов
- кэширование/переиспользование market/snapshot/candle данных (DMS + candles_cache)
- backoff/retry на части операций (scheduler/session loops)
- ограничение частоты торговых циклов через `update_interval_seconds` и scheduler interval

## 25.3 Что считается признаком упора в лимиты

Операционные индикаторы:

- рост ошибок `HTTP 429`/transport timeout у брокера или MOEX
- скачок reconnect/re-subscribe в websocket слоях
- рост времени выполнения П1/П2 и trading cycle
- деградация preview/initialize-day при пиковых нагрузках

## 25.4 Операторские рекомендации

- не запускать массово force-run для большого числа роботов одновременно
- при изменениях universe/filters запускать staggered (волнами)
- при признаках rate limit временно увеличить интервалы пересчёта:
  - `paper_selection.refresh.every_minutes`
  - цикл робота / update interval

---

## 26. Изменение полей во время активной сессии

## 26.1 Общий принцип

Торговая сессия периодически подтягивает актуальный `config` из БД (`refresh_config` в `TradingSession`), поэтому часть изменений применяется **на лету**, часть — только в следующем цикле/сессии.

## 26.2 Что применяется на лету

В рамках текущей live-сессии, после refresh:

- `allowed_figis`:
  - сессия видит новый список
  - websocket может выполнить переподписку
- `strategy_params.interval`:
  - меняется candle interval для подписки
- параметры стратегии/риска:
  - учитываются в следующих торговых циклах
- universe jobs state:
  - П1/П2 могут дообновить конфиг и снова примениться без рестарта процесса

## 26.3 Что фактически требует нового запуска

Операторски стоит считать restart-required для:

- смены токена/критичной broker auth-конфигурации
- крупных структурных изменений стратегии, когда нужно "чистое" состояние
- смены типа робота/базовых сущностей (через recreate/update flow)

На практике safest путь для критичных изменений:

1. остановить робота (status OFF),
2. сохранить настройки,
3. снова запустить.

## 26.4 UX-ограничение

UI уже страхует некорректный запуск:

- требует успешный `Проверить` перед `Запустить`
- при редактировании выполняет autosave, что может менять конфиг во время работы

Поэтому важно для операторов: если правка критична, лучше делать controlled restart, а не hot-change в активной сессии.

---

## 27. Force-run endpoint'ы: операторский runbook

В системе есть два служебных endpoint'а для принудительного запуска.

## 27.1 `GET /api/scheduler/portfolio/run`

Назначение:

- немедленно выполнить **один цикл** `PortfolioUpdaterScheduler.run_once()`
- полезно после обновления токена/счета, перед запуском торговой сессии

Ожидаемый ответ:

- агрегат по циклу (`total`, `processed`, `skipped`, `errors`)

Когда использовать:

- первичная синхронизация портфелей
- диагностика "почему не обновляются snapshot'ы"

Риски:

- может сделать много внешних вызовов при большом числе активных `type=1`

## 27.2 `GET /api/scheduler/trading/run/{robot_id}`

Назначение:

- принудительно запустить торговую сессию для конкретного `robot_id`
- обходит ожидание следующего scheduler-цикла

Ожидаемый ответ:

- `status=success` при запуске/выполнении
- `status=error` если робот не найден/недоступен

Когда использовать:

- оперативный ручной старт после правок конфигурации
- проверка конкретного робота без ожидания общего расписания

Риски:

- если одновременно выполняются массовые force-run, возрастает нагрузка и вероятность rate limit
- нужно убедиться, что робот корректно настроен (`Проверить`/config/schedule)

## 27.3 Безопасный порядок для оператора

Рекомендуемый последовательный сценарий:

1. Проверить, что у робота валидный token/config/schedule.
2. Выполнить `GET /api/scheduler/portfolio/run` (по необходимости синхронизации).
3. Проверить snapshot/live состояние (`/api/robots/live/snapshot`).
4. Выполнить `GET /api/scheduler/trading/run/{robot_id}`.
5. Наблюдать WS/логи первые 1-2 цикла (errors, order statuses, queue health).

---

## 28. Operator anti-patterns (чего избегать)

Ниже список типичных действий, которые приводят к инцидентам или деградации.

## 28.1 Массовый force-run в один момент

Проблема:

- резкий всплеск внешних API-запросов (broker/MOEX)
- повышенный риск rate limit, timeouts и деградации websocket

Как правильно:

- запускать волнами (batch/staggered), а не одновременно по всем роботам
- начинать с роботов наибольшего приоритета

## 28.2 Изменение критичных полей «на горячую» без controlled restart

Проблема:

- сессия часть изменений подхватит в следующих циклах, часть — нет мгновенно
- оператор получает непредсказуемый runtime-результат

Как правильно:

- для критичных правок (token/broker/структура стратегии) делать:
  - stop -> save -> start

## 28.3 Запуск робота без предварительной проверки

Проблема:

- UI-блокировки обходятся не всегда (через ручные вызовы/API)
- можно получить `allowed_figis` пустой, невалидный schedule или неконсистентный config

Как правильно:

- перед запуском всегда выполнять check flow:
  - локальная валидация
  - preview pipeline (для П2)
  - проверка token + schedule

## 28.4 Одновременный пересчет П1/П2 в market open

Проблема:

- нагрузка на DMS/snapshot/candles cache именно в момент, когда trade loop тоже активно работает

Как правильно:

- П1 делать до открытия сессии (через `daily_at_msk`)
- П2 запускать по интервалу и без «шторма» ручных перезапусков

## 28.5 Игнорирование признаков stale-состояния pipeline

Проблема:

- робот торгует на устаревшем candidate_pool/allowed_figis

Как правильно:

- мониторить `last_historical_screening_at` и `last_paper_selection_at`
- при stale делать controlled re-run П1/П2

---

## 29. Блокировки запуска: UI и backend

Раздел фиксирует все фактические “stop conditions”, при которых запуск должен быть остановлен или отклонен.

## 29.1 UI-блокировки (до нажатия «Запустить»)

На уровне формы запуск блокируется при:

- `lastCheckOk !== true` (кнопка `Проверить` не пройдена)
- не сохранен новый робот (`isNewRobot || !selectedRobot`)
- есть blocking-ошибки `severity=error`:
  - пустое имя
  - не выбран token
  - неверные часы работы
  - не задан fixed ticker list в режиме `fixed`
  - ошибки параметров стратегии/риска
- неуспешный preview П2 (`/dms/pipeline/preview`) для не-fixed режима

Сообщение UI: сначала пройти `Проверить`, затем запуск.

## 29.2 API/WS-блокировки (runtime)

На backend запуск/работа фактически блокируются при:

- websocket auth fail (`/ws/live` -> `Unauthorized`)
- робот не найден или не `type=2` для live ws
- пустой universe (`allowed_figis` не заполнен и не удалось autofill)
- ошибка broker websocket connect

В ответ клиенту уходят `error` сообщения и соединение закрывается.

## 29.3 Session-level блокировки в trading

`TradingSession.run()` не продолжит нормальный цикл при:

- отсутствует `account_id` и не удалось автоподобрать счет
- `allowed_figis` пустой после sync/universe refresh
- критическая ошибка в websocket/trading worker

Итог:

- сессия завершится с ошибкой/partial
- это отражается в execution logs и UI-статусе сессии

## 29.4 Scheduler-level ограничения запуска

`TradingScheduler` не запустит новую сессию если:

- для этого `robot_id` уже есть активная task (`active_sessions`)
- робот вне разрешенного schedule window (`should_start_trading_session=false`)

Это защищает от дублей сессий и запуска вне торгового окна.

## 29.5 Операторская матрица блокировок (кратко)

- **Config invalid** -> исправить поля -> `Проверить` -> сохранить.
- **Universe empty** -> выполнить П1/П2 (или sync-universe) -> проверить `allowed_figis`.
- **Schedule closed** -> дождаться окна или временно скорректировать расписание.
- **Active session exists** -> не force-run повторно; дождаться завершения/остановить штатно.
- **Broker/WS недоступен** -> не перезапускать массово, сначала стабилизировать внешний контур.

---

## 30. Config v3, UI profiles и операции (as-is, 2026)

Дополнение к target `ROBOTS-ARCHITECTURE-TARGET.md` §8, §15, §17.

### 30.1 Профили config (`schema_profile`)

| Профиль | type | broker | Назначение |
|---------|------|--------|------------|
| `type1_tinvest` | 1 | tinvest | Portfolio updater T-Invest |
| `type1_bybit` | 1 | bybit | Portfolio updater ByBit |
| `type2_tinvest` | 2 | tinvest | Trading MOEX (П1/П2/П3, DMS) |
| `type2_bybit` | 2 | bybit | Trading crypto (symbols, funding) |

Новые роботы из UI сохраняются с `config_version: 3`. Legacy v2 в БД — `POST /api/robots/migrate-config-v3`.

### 30.2 UI: `deriveMarketProfile`

| Профиль | Видимые блоки |
|---------|---------------|
| `portfolio` | `PortfolioConfigurator`, расписание sync |
| `moex` | П1/П2/П3, DMS, FIGI, НДФЛ |
| `crypto` | `CryptoConfigurator`, symbols, leverage, fees, 24/7 |

`broker_type` неизменяем после создания. Смена брокера — `POST /api/robots/duplicate`.

### 30.3 REST

| Endpoint | Назначение |
|----------|------------|
| `POST /api/robots/duplicate` | Копия: strategy/risk/costs/schedule; reset universe |
| `POST /api/robots/validate-config` | Validate без save; OpenAPI oneOf |
| `GET /api/robots/config-schema/{schema_profile}` | JSON Schema профиля |

### 30.4 Crypto (type2_bybit)

- Backtest: crypto prefetch, funding в `BacktestTradingSession`
- `GET /api/bybit/funding-rate`
- Testnet/Mainnet badge на `/robots` и `/live`

### 30.5 Frontend builders

| Builder | Профиль |
|---------|---------|
| `buildPortfolioRobotConfig` | type1_* |
| `buildTradingRobotConfig` / `buildMoexConfig` | type2_tinvest |
| `buildCryptoTradingRobotConfig` | type2_bybit |

