# Приёмочный чеклист: унифицированный UI `/testing`

**Версия:** 1.0  
**Дата:** 18.06.2026  
**Назначение:** единый чеклист для приёмки всего скопа T0–T6 (backend + as-built UI + refactored UI).

**Связанные документы:**

- [TESTING-UI-RELEASE_MAP.md](TESTING-UI-RELEASE_MAP.md) — план этапов
- [TESTING-UI-RELEASE_STATUS.md](TESTING-UI-RELEASE_STATUS.md) — трекинг задач
- [TESTING-BACKTEST-REFERENCE.md](TESTING-BACKTEST-REFERENCE.md) — as-built API и фазы
- [TESTING-UI-BACKEND-CHANGES.md](TESTING-UI-BACKEND-CHANGES.md) — спека T0 backend

**Легенда статусов:** ✅ done · 🟡 partial · ⬜ pending · 🔲 manual (ручная проверка)

---

## 0. Мета и окружение

| Поле | Значение |
|------|----------|
| Окружение | `test_db` / schema `ganaly`, backend + frontend dev |
| MOEX токен | T-Invest `api_tokens` (prod/sandbox по настройке) |
| Crypto токен | ByBit testnet `api_tokens.id=25` (или свой) |
| Feature flag refactored UI | **По умолчанию** на `/testing` (T6.1). Legacy: `VITE_TESTING_LEGACY=true` |
| Дата прогона приёмки | __________ |
| Подпись | __________ |

---

## 1. T0 — Backend: crypto auto-screening

| # | Критерий | Статус | Примечание |
|---|----------|--------|------------|
| T0.1 | `universe_mode` crypto: `fixed` \| `auto` в config v3 | ✅ | `universe.py`, `type2_bybit.py` |
| T0.2 | Scoring branch для crypto auto в history-backtest | ✅ | `service.py`, `crypto_universe_scoring.py` |
| T0.3 | Per-day universe из `crypto_universe_daily` (с robot_id) | ✅ | |
| T0.4 | Ad-hoc без robot_id — on-the-fly screening | 🟡 | In-memory; без миграции `run_id` |
| T0.5 | Документация ограничений M2 (point-in-time) | 🟡 | §10 в REFERENCE — проверить актуальность |
| T0.6 | Unit-тесты crypto scoring | ✅ | `test_crypto_universe_scoring_backtest.py` |
| T0.7 | Прогресс scoring crypto в poll API | 🟡 | BE done; UI poll не подтверждён вручную |
| T0.8 | Фильтр истории `broker_type` на API | ✅ | `test_backtest_history_broker_filter.py` |

### Ручной smoke T0 (crypto auto)

- [ ] 🔲 `POST /api/robots/history-backtest` с `broker_type=bybit`, `universe_mode=auto`, `min_volume_24h_usd`, `max_spread_bps` → HTTP 202
- [ ] 🔲 Poll `GET .../runs/{id}/status` — фаза `scoring` не instant-skip
- [ ] 🔲 Terminal `SUCCESS` — `allowed_figis_by_date` не пустой (или понятный `FAILED`/`422` без токена)
- [ ] 🔲 Без ByBit токена → `422` с текстом про `api_tokens`

---

## 2. T1 — Foundation: типы, хуки, payload

| # | Критерий | Статус | Артефакт |
|---|----------|--------|----------|
| T1.1 | TypeScript types (`FormState`, requests, responses) | ✅ | `refactored/types/` |
| T1.2 | `useTestingConfig` — validate + payload | ✅ | `hooks/useTestingConfig.ts` |
| T1.3 | `useTestingRunner` — run + poll 2s × 7200 + cancel + resume | ✅ | `hooks/useTestingRunner.ts` |
| T1.4 | `useTestingResults` — history, filters, compare, ingest | ✅ | `hooks/useTestingResults.ts` |
| T1.5 | `payloadBuilder.ts` → `buildTradingRobotConfig` | ✅ | `refactored/payloadBuilder.ts` |
| T1.6 | `validation.ts` — период ≤365, universe, max_daily_loss % | ✅ | `refactored/validation.ts` |
| T1.7 | `defaults.ts` — пресеты MOEX/crypto | ✅ | `refactored/defaults.ts` |
| T1.8 | Feature flag / cutover | ✅ | T6.1 default refactored; `/testing-v2` → redirect |

### Регрессия T1 / T6.1

- [ ] 🔲 `/testing` без env — refactored wizard UI (`useTestingRefactoredPage`)
- [ ] 🔲 `VITE_TESTING_LEGACY=true` — legacy `useTestingPage`
- [ ] 🔲 `/testing-v2` редирект на `/testing`
- [ ] 🔲 MOEX ad-hoc backtest — payload идентичен legacy builder (Network tab)
- [x] ✅ `npm run build` — без ошибок TypeScript

### Автотесты T1 (backlog)

- [ ] ⬜ Unit: `validateTestingForm` (period, fixed universe, max_daily_loss %)
- [ ] ⬜ Unit: `buildBacktestConfigFromForm` snapshot vs legacy builder
- [ ] ⬜ Mock: `pollUntilTerminal` terminal set

---

## 3. As-built UI (до wizard) — уже в проде на `/testing`

| # | Критерий | Статус | Примечание |
|---|----------|--------|------------|
| A.1 | Crypto universe `fixed` + `auto` в форме | ✅ | `TestingUniverseModeCard` |
| A.2 | Поля min volume / max spread bps для crypto auto | ✅ | |
| A.3 | `max_daily_loss` — **проценты**, label в UI | ✅ | `TestingRiskParamsCard` |
| A.4 | Фильтр истории по рынку (MOEX/Crypto/Все) | ✅ | `TestingBacktestHistoryCard` |
| A.5 | Колонка «Рынок» в истории | ✅ | `broker_type` / `market_profile` |
| A.6 | Явный `MarketSelector` (первый контрол) | ✅ | T2.1 — над config stage |
| A.7 | Wizard Setup → Run → Analysis | ⬜ | T3 |

---

## 4. T2 — Setup UI (wizard, панели)

| # | Критерий | Статус |
|---|----------|--------|
| T2.1 | `MarketSelector` MOEX / Crypto | ✅ |
| T2.2 | `BaseConfigPanel` | ✅ |
| T2.3 | `MoexExtendedPanel` | ✅ |
| T2.4 | `CryptoExtendedPanel` | ✅ |
| T2.5 | Crypto auto UI в wizard panel | ✅ |
| T2.6 | `StrategyParamsPanel` | ✅ |
| T2.7 | `RiskManagementPanel` (max daily **%**) | ✅ |
| T2.8 | Collapsible sections | ✅ |
| T2.9 | «Сохранить как робота» | 🟡 | as-built |
| T2.10 | Кнопка «Проверить» (validate без run) | ✅ |

### T2.1 — MarketSelector (ручная приёмка)

| # | Шаг | Ожидание | Статус |
|---|-----|----------|--------|
| M.1 | Открыть `/testing` — блок «РЫНОК» первый под заголовком | MOEX выбран, валюта **₽** | 🔲 |
| M.2 | Переключить на **Crypto** | Валюта **USDT**; брокер ByBit; бюджет ~10 000; стратегия crypto-пресет | 🔲 |
| M.3 | Вернуть **MOEX** | Валюта **₽**; брокер T-Invest; бюджет ~1 000 000; grain_seed risk | 🔲 |
| M.4 | Выбрать MOEX-робота → переключить на Crypto | Toast «Робот снят»; robot = ad-hoc; crypto presets | 🔲 |
| M.5 | Список роботов | Показываются только роботы выбранного рынка | 🔲 |
| M.6 | MOEX: dropdown брокера | T-Invest + Sandbox (без ByBit) | 🔲 |
| M.7 | Crypto: dropdown брокера | Только ByBit | 🔲 |
| M.8 | `/testing-v2` — те же пункты M.1–M.7 | Поведение идентично | 🔲 |

### T2.2 — BaseConfigPanel (ручная приёмка)

| # | Шаг | Ожидание | Статус |
|---|-----|----------|--------|
| B.1 | Карточка «БАЗОВАЯ КОНФИГУРАЦИЯ» — первая в левой колонке | Robot, strategy, capital, period, universe в одной карточке | 🔲 |
| B.2 | Ad-hoc (без робота) | Поля редактируются; grain_seed / crypto presets | 🔲 |
| B.3 | Выбор робота type=2 | Гидратация strategy, capital, universe из config | 🔲 |
| B.4 | Бюджет только в BaseConfig | В «Риск-менеджмент» поля capital нет | 🔲 |
| B.5 | Universe | В BaseConfig; отдельной карточки universe справа нет | 🔲 |
| B.6 | «Брокер и расписание» | Отдельная карточка ниже (broker, poll, session) | 🔲 |
| B.7 | Payload regression | `buildTradingRobotConfig` без изменений vs до T2.2 | 🔲 |

### T2.3 / T2.4 — Extended panels (ручная приёмка)

| # | Шаг | Ожидание | Статус |
|---|-----|----------|--------|
| E.1 | MOEX: правая колонка | Карточка «MOEX — РАСШИРЕННЫЕ»: сессия, НДФЛ, weekdays, universe refresh | 🔲 |
| E.2 | MOEX: pipeline | При universe `dms_pipeline` — блок пайплайна внутри MOEX extended | 🔲 |
| E.3 | MOEX: НДФЛ не в риске | В «Риск-менеджмент» нет поля НДФЛ | 🔲 |
| E.4 | Crypto: правая колонка | «CRYPTO — РАСШИРЕННЫЕ»: testnet, category, leverage, funding, maker/taker | 🔲 |
| E.5 | Комиссия в риске (оба рынка) | Поле «Комиссия брокера (%)» видно и на MOEX, и на Crypto | 🔲 |
| E.6 | «Брокер и расписание» | Только broker + poll + create robot (без сессии/weekdays) | 🔲 |

### T2.6–T2.8 — Strategy/Risk + collapsible (ручная приёмка)

| # | Шаг | Ожидание | Статус |
|---|-----|----------|--------|
| S.1 | Секция «Стратегия и риск» | Открыта по умолчанию; Strategy + Risk panels | 🔲 |
| S.2 | Risk label | «Макс. дневной убыток, %» (с запятой) | 🔲 |
| S.3 | Комиссия | В Risk panel на MOEX и Crypto | 🔲 |
| S.4 | Секция «Расширенные» | Свернута по умолчанию; раскрывается по клику | 🔲 |
| S.5 | В «Расширенных» | Broker, MOEX/Crypto extended, cache, universe LIVE, recommendations | 🔲 |
| S.6 | Базовый блок | Market + BaseConfig всегда видны (вне accordion) | 🔲 |

### T2.10 — «Проверить» (ручная приёмка)

| # | Шаг | Ожидание | Статус |
|---|-----|----------|--------|
| V.1 | Кнопка «Проверить» | Между Setup и run bar; без HTTP | 🔲 |
| V.2 | Пустой период | Toast с ошибкой; подсветка period | 🔲 |
| V.3 | Валидная форма | Toast success «Конфигурация готова…» | 🔲 |
| V.4 | Crypto fixed без символов | Ошибка universe | 🔲 |
| V.5 | Во время run | Кнопка disabled | 🔲 |

---

## 5. T3 — Run UI

| # | Критерий | Статус |
|---|----------|--------|
| T3.1 | `TestingWizard` shell | ✅ | stepper + auto Run/Analysis |
| T3.2 | `RunControlPanel` | ✅ | IDLE/RUNNING/terminal + sticky Run |
| T3.3 | Phase stepper (7 фаз) | ✅ | `RunPhaseStepper` + weights from backend |
| T3.4 | ETA + progress bar | ✅ | `RunControlPanel` + poll status |
| T3.5 | Cancel run | ✅ | as-built |
| T3.6 | Resume on mount (active run) | ✅ | legacy + refactored runner |
| T3.7 | Persist dirty config before run | ✅ | as-built |

| W.1 | Stepper виден | Setup / Run / Analysis | 🔲 |
| W.2 | «Запустить бэктест» на Setup | Переход на Run + старт poll | 🔲 |
| W.3 | После SUCCESS | Авто-переход на Analysis | 🔲 |
| W.4 | Resume active run | При mount → шаг Run | 🔲 |
| W.5 | Analysis без result | Шаг disabled в stepper | 🔲 |
| W.6 | История → открыть run | Шаг Analysis + результат | 🔲 |

| R.1 | Run step only | Sticky bar виден только на Run | 🔲 |
| R.2 | IDLE | «Ожидание запуска», кнопка активна | 🔲 |
| R.3 | RUNNING | Progress + «Стоп» + pulse dot | 🔲 |
| R.4 | SUCCESS terminal | Badge «Результат готов» | 🔲 |
| R.5 | ERROR terminal | Badge «Ошибка запуска» + текст | 🔲 |
| R.6 | «← Настройка» | Возврат на Setup без сброса формы | 🔲 |

| P.1 | 7 фаз видны на Run | Подготовка → … → Сохранение | 🔲 |
| P.2 | Active phase | ⏳ на текущей фазе | 🔲 |
| P.3 | Done phases | ✅ на пройденных | 🔲 |
| P.4 | Веса фаз | 4/12/36/10/8/28/2 % | 🔲 |
| P.5 | Шаг фазы | N/M на active при units | 🔲 |
| P.6 | SUCCESS | Все 7 ✅ | 🔲 |

---

## 6. T4 — Analysis UI

| # | Критерий | Статус |
|---|----------|--------|
| T4.1 | `ResultsDashboard` / KPI | ✅ | 6 tiles + pipeline stats |
| T4.2 | `EquityChart` | ✅ | `EquityChartPanel` |
| T4.3 | Tabs: trades / signals / orders / portfolio | ✅ | `ResultDetailsTabs` |
| T4.4 | Export JSON / Download | ✅ | `ResultExportActions` |
| T4.5 | `HistoryPanel` + фильтр рынка | ✅ | wrapper + as-built |
| T4.6 | Compare runs | ✅ | `RunComparePanel` + API |
| T4.7 | Валюта KPI RUB / USDT | ✅ | `resolveResultCurrencyLabel` |

| A.1 | 6 KPI на Analysis | return, Sharpe, DD, win rate, PF, equity | 🔲 |
| A.2 | Export | Копировать / Скачать JSON | 🔲 |
| A.3 | Compare | Δ метрик через API при выборе 2 run | 🔲 |
| A.4 | Валюта | USDT для crypto, ₽ для MOEX | 🔲 |

---

## 7. T5 — Advanced accordion

| # | Критерий | Статус |
|---|----------|--------|
| T5.1 | `AdvancedPanel` (collapsed default) | ✅ | badge «Опционально» |
| T5.2 | MOEX cache в Advanced | ✅ | MOEX only |
| T5.3 | Universe LIVE в Advanced | ✅ | MOEX only |
| T5.4 | Recommendations в Advanced | ✅ | hint без result |
| T5.5 | Shared cards в TradingRobotSettings | ✅ | без изменений |

| ADV.1 | «Дополнительно» collapsed | Badge «Опционально» | 🔲 |
| ADV.2 | MOEX Setup | Cache + Universe только в Advanced | 🔲 |
| ADV.3 | Crypto Setup | Advanced = рекомендации | 🔲 |
| ADV.4 | Расширенные | Без cache/universe внутри | 🔲 |

---

## 8. T6 — Cutover и финальная приёмка

| # | Критерий | Статус |
|---|----------|--------|
| T6.1 | Feature flag flip (refactored = default) | ✅ | `featureFlag.ts`, `/testing-v2` redirect |
| T6.2 | E2E MOEX backtest | 🔲 | §9.1–9.2 manual |
| T6.3 | E2E Crypto fixed + auto | 🔲 | §9.3–9.4 manual |
| T6.4 | Regression TradingRobotSettings | 🔲 | §9 + Settings smoke |
| T6.5 | Документация актуальна | ✅ | RELEASE_STATUS, checklist |
| T6.6 | Deprecate legacy hooks | ✅ | `@deprecated` useTestingPage/Backtest |
| T6.7 | Чеклист + RELEASE_STATUS | ✅ | синхронизировано |

---

## 9. Сквозные сценарии (E2E manual)

### 9.1 MOEX grain_seed (ad-hoc)

1. Открыть `/testing`, период ≤30 дней, стратегия `grain_seed`, universe `dms_pipeline`
2. Запустить backtest → HTTP 202
3. Дождаться `SUCCESS` — KPI, equity chart, trades
4. История — запись с `broker_type=tinvest`

- [ ] 🔲 Пройдено

### 9.2 MOEX с роботом type=2

1. Выбрать существующего робота type=2
2. Изменить параметр → config dirty → run
3. Config сохранён на робота перед run

- [ ] 🔲 Пройдено

### 9.3 Crypto fixed (ByBit testnet)

1. Broker ByBit, universe `fixed`, символы `BTCUSDT`
2. Token id=25 (или свой testnet)
3. Run → SUCCESS, funding учтён в симуляции

- [ ] 🔲 Пройдено

### 9.4 Crypto auto

1. Universe `auto`, min volume 5M USD, max spread 30 bps
2. Run → scoring не пустой → симуляция
3. История — фильтр «Crypto»

- [ ] 🔲 Пройдено

### 9.5 Отмена и partial

1. Длинный период → Cancel во время run
2. `cancel_requested` в status; terminal с `partial_result` при необходимости

- [ ] 🔲 Пройдено

### 9.6 Refactored cutover (T6.1)

1. Открыть `/testing` — wizard Setup / Run / Analysis, refactored hooks
2. `/testing-v2` → redirect на `/testing`
3. `VITE_TESTING_LEGACY=true` — flat legacy controller (fallback 1 релиз)

- [ ] 🔲 Пройдено

---

## 10. API regression (контракты не меняются)

| Endpoint | Проверка | Статус |
|----------|----------|--------|
| `POST /api/robots/history-backtest` | 202 + `run_id` | 🔲 |
| `GET .../runs/{id}/status` | poll fields | 🔲 |
| `GET .../runs/{id}` | details payload | 🔲 |
| `POST .../runs/{id}/cancel` | cancel | 🔲 |
| `GET .../runs/active` | resume | 🔲 |
| `POST /api/robots/history-backtest/list` | `broker_type` filter | 🔲 |

---

## 11. Продуктовые инварианты (зафиксированные решения)

| Инвариант | Проверка | Статус |
|-----------|----------|--------|
| `max_daily_loss` — **%**, не ₽/USDT | UI label + config field | ✅ |
| Crypto auto — backend scoring, не UI-only | T0 scoring branch | ✅ |
| MoexCache / Universe / Recommendations — Advanced (свёрнуто) | T5 | ✅ |
| Crypto historical screening — модель M2 (point-in-time) | docs §10 | 🟡 |

---

## 12. Сводка готовности к релизу

| Release | Готово для приёмки | Блокеры |
|---------|-------------------|---------|
| T0 | 🟡 ~85% | E2E crypto auto, T0.4 migration, UI poll T0.7 |
| T1 | ✅ ~95% | Unit-тесты validate/payload (опционально) |
| As-built UI | 🟡 ~75% | Wizard; MarketSelector ✅ |
| T2 Setup | ✅ ~95% | T2.1–T2.10 ✅; T2.9 в extended |
| T3–T5 | ⬜ | — |
| T6 cutover | ⬜ | T2–T5 + E2E |

**Минимум для MVP-A (MOEX only):** T0 не блокирует; T1 + as-built MOEX E2E ✅  
**Минимум для MVP-B (Crypto auto):** T0 E2E + сценарий 9.4 ✅

---

*Обновлять этот файл при закрытии каждого пункта RELEASE_STATUS. Дата последнего обновления: 18.06.2026.*
