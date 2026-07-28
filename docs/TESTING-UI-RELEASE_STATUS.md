# TESTING UI — Release Status



Источник плана: [TESTING-UI-RELEASE_MAP.md](TESTING-UI-RELEASE_MAP.md).  

Приёмка: [TESTING-UI-ACCEPTANCE-CHECKLIST.md](TESTING-UI-ACCEPTANCE-CHECKLIST.md).  

Изменения backend: [TESTING-UI-BACKEND-CHANGES.md](TESTING-UI-BACKEND-CHANGES.md).



**Обновлено:** 18.06.2026



---



## T0 — Backend: crypto auto-screening в history-backtest



### T0.1 — Расширить `universe_mode` для crypto

- **Status**: ✅ done



#### DoD

- [x] `normalize_crypto_universe_mode` / crypto-ветка возвращает `fixed` или `auto`

- [x] `validate_robot_config` для `type2_bybit` принимает `universe_mode=auto`

- [x] Unit-тест на нормализацию



---



### T0.2 — Scoring branch для crypto auto

- **Status**: ✅ done



#### DoD

- [x] Crypto `fixed` — поведение без регрессии

- [x] Crypto `auto` — не instant-skip scoring

- [x] Пустой universe после auto → понятный `422`/`FAILED`



---



### T0.3 — Per-day universe из `crypto_universe_daily`

- **Status**: ✅ done



---



### T0.4 — On-the-fly screening для ad-hoc

- **Status**: 🟡 partial (in-memory; без миграции `run_id`)



#### DoD

- [x] `POST /history-backtest` без `robot_id`, `universe_mode=auto`

- [x] Нет токена ByBit → `422`

- [ ] Миграция `run_id` на `crypto_universe_daily` (опционально)



---



### T0.5 — Документация ограничений

- **Status**: 🟡 partial



#### DoD

- [x] [TESTING-BACKTEST-REFERENCE.md](TESTING-BACKTEST-REFERENCE.md) §10 — подраздел crypto auto

- [ ] [TESTING-UI-BACKEND-CHANGES.md](TESTING-UI-BACKEND-CHANGES.md) §6 — финальная синхронизация



---



### T0.6 — Тесты crypto auto backtest

- **Status**: ✅ done (unit); e2e — pending



#### DoD

- [x] `test_crypto_universe_scoring_backtest.py`

- [ ] Integration e2e против реального ByBit/DB



---



### T0.7 — Прогресс scoring для crypto

- **Status**: 🟡 partial



#### DoD

- [x] `_flush_backtest_progress` по дням

- [ ] UI poll вручную подтверждён для crypto auto



---



### T0.8 — Фильтр истории по рынку

- **Status**: ✅ done



#### Артефакты

- `backend/app/modules/robots/schemas.py` — `broker_type` filter, поля в item

- `backend/app/modules/robots/service.py` — `get_backtest_history`

- `frontend` — `historyMarketFilter`, колонка «Рынок»

- `backend/tests/test_backtest_history_broker_filter.py`



#### DoD

- [x] Фильтр `tinvest` | `bybit` | all

- [x] `broker_type` / `market_profile` в ответе

- [x] Обратная совместимость



---



## T1 — Foundation: типы, хуки, payload



### T1.1 — TypeScript types

- **Status**: ✅ done

- **Артефакты**: `frontend/src/pages/testing/refactored/types/{forms,requests,responses}.ts`



#### DoD

- [x] `TestingFormState`, `UnifiedHistoryBacktestRequest`

- [x] `maxDailyLossPct` как **percent**



---



### T1.2 — `useTestingConfig`

- **Status**: ✅ done

- **Артефакт**: `refactored/hooks/useTestingConfig.ts`



---



### T1.3 — `useTestingRunner`

- **Status**: ✅ done

- **Артефакты**: `refactored/hooks/useTestingRunner.ts`, `refactored/runner/pollUntilTerminal.ts`



#### DoD

- [x] Poll 2s, max 7200, terminal set

- [x] Cancel, resume on mount



---



### T1.4 — `useTestingResults`

- **Status**: ✅ done

- **Артефакт**: `refactored/hooks/useTestingResults.ts`



---



### T1.5 — `payloadBuilder.ts`

- **Status**: ✅ done

- **Артефакт**: `refactored/payloadBuilder.ts`



#### DoD

- [x] Делегирует `buildTradingRobotConfig`

- [ ] Snapshot unit-тесты (backlog)



---



### T1.6 — `validation.ts`

- **Status**: ✅ done

- **Артефакт**: `refactored/validation.ts`



---



### T1.7 — `defaults.ts`

- **Status**: ✅ done

- **Артефакт**: `refactored/defaults.ts`



---



### T1.8 — Feature flag

- **Status**: ✅ done



#### DoD

- [x] `VITE_TESTING_REFACTOR` — `featureFlag.ts`, `vite-env.d.ts`

- [x] Маршрут `/testing-v2` → `TestingRefactoredPage`

- [x] Legacy `/testing` по умолчанию



#### Артефакты

- `refactored/hooks/useTestingRefactoredPage.ts` — композиция 3 хуков

- `refactored/formAdapter.ts` — мост с `useTestingRobotForm`



---



## As-built UI (параллельно T1, не wizard)



| Задача | Статус |

|--------|--------|

| Crypto auto/fixed в `TestingUniverseModeCard` | ✅ |

| `max_daily_loss` % в `TestingRiskParamsCard` | ✅ |

| История + фильтр рынка | ✅ |



---



## T2 — Setup UI

### T2.1 — `MarketSelector`
- **Status**: ✅ done

#### Артефакты
- `refactored/components/MarketSelector.tsx`, `refactored/market.ts`
- `useTestingRobotForm` — `market`, `setMarket`
- `TestingPageContent` — первый контрол; фильтр роботов

#### DoD
- [x] MOEX / Crypto, валюта ₽ / USDT
- [x] Сброс incompatible robot + toast
- [ ] Ручная приёмка M.1–M.8 (ACCEPTANCE-CHECKLIST §4)

### T2.2 — `BaseConfigPanel`
- **Status**: ✅ done

#### Артефакты
- `refactored/components/setup/BaseConfigPanel.tsx`
- `TestingUniverseModeFields.tsx` — shared universe fields
- `TestingRobotParamsCard` → «Брокер и расписание» (extended, T2.3 prep)
- `TestingRiskParamsCard` — `showCapital={false}` на `/testing`

#### DoD
- [x] Robot, strategy, period, capital, universe mode в одной панели
- [x] Ad-hoc + гидратация из robot (через `useTestingRobotForm`)
- [ ] Ручная приёмка B.1–B.7 (ACCEPTANCE-CHECKLIST §4)

### T2.3 — `MoexExtendedPanel`
- **Status**: ✅ done
- **Артефакт**: `refactored/components/setup/MoexExtendedPanel.tsx`
- DoD: сессия MSK, weekdays, НДФЛ, universe refresh, pipeline (embedded)

### T2.4 — `CryptoExtendedPanel`
- **Status**: ✅ done
- **Артефакт**: `refactored/components/setup/CryptoExtendedPanel.tsx`
- DoD: testnet, category, leverage, funding, maker/taker fees

| Задача | Статус |
|--------|--------|
### T2.5 — Crypto auto в BaseConfig
- **Status**: ✅ done (поля в `BaseConfigPanel` / universe fields)

### T2.6 — `StrategyParamsPanel`
- **Status**: ✅ done
- **Артефакт**: `refactored/components/setup/StrategyParamsPanel.tsx`

### T2.7 — `RiskManagementPanel`
- **Status**: ✅ done
- **Артефакт**: `refactored/components/setup/RiskManagementPanel.tsx`
- Label: «Макс. дневной убыток, %»; комиссия для обоих рынков

### T2.8 — Collapsible sections
- **Status**: ✅ done
- **Артефакт**: `TestingSetupCollapsible.tsx`
- «Стратегия и риск» — open; «Расширенные» — collapsed

| Задача | Статус |
|--------|--------|
### T2.10 — «Проверить»
- **Status**: ✅ done
- **Артефакты**: `SetupValidateBar.tsx`, `setupValidation.ts`
- DoD: `validateTestingForm` + toast; без network; подсветка `form.invalid`

| Задача | Статус |
|--------|--------|
| T2.9 «Сохранить как робота» | 🟡 (в extended) |



---



## T3 — Run UI

### T3.1 — `TestingWizard` shell
- **Status**: ✅ done
- **Артефакты**: `TestingWizard.tsx`, `TestingWizardStepper.tsx`, `useTestingWizardStep.ts`, `wizard/types.ts`
- DoD: stepper Setup/Run/Analysis; Setup→Run по «Запустить бэктест»; Run→Analysis при завершении; resume на Run при active poll

| Задача | Статус |
|--------|--------|
### T3.2 — `RunControlPanel`
- **Status**: ✅ done
- **Артефакты**: `RunControlPanel.tsx`, `RunStatusLog.tsx`, `runControlState.ts`
- DoD: IDLE / RUNNING / success|error terminal; sticky на этапе Run; «← Настройка»

| Задача | Статус |
|--------|--------|
| T3.1 wizard shell | ✅ |
### T3.3 — Phase stepper
- **Status**: ✅ done
- **Артефакты**: `RunPhaseStepper.tsx`, `backtestPhases.ts`
- DoD: 7 фаз с ✅/⏳; веса из `backtest_progress.py`; `run_phase` из poll

| Задача | Статус |
|--------|--------|
| T3.2 `RunControlPanel` | ✅ |
| T3.3 phase stepper | ✅ |
| T3.4 ETA + progress | ✅ |
| T3.5–T3.7 cancel, resume, persist | ✅ (as-built + T1 runner) |



---



## T4 — Analysis UI

### T4 — `TestingAnalysisPanel`
- **Status**: ✅ done
- **Артефакты**: `TestingAnalysisPanel`, `ResultsDashboard`, `EquityChartPanel`, `ResultDetailsTabs`, `ResultExportActions`, `RunComparePanel`, `HistoryPanel`
- DoD: 6 KPI; export JSON; compare API; валюта RUB/USDT

| Задача | Статус |
|--------|--------|
| T4.1 ResultsDashboard | ✅ |
| T4.2 EquityChartPanel | ✅ |
| T4.3 ResultDetailsTabs | ✅ |
| T4.4 Export | ✅ |
| T4.5 HistoryPanel | ✅ |
| T4.6 Compare API | ✅ |
| T4.7 Currency label | ✅ |



---



## T5 — Advanced accordion

### T5 — `AdvancedPanel`
- **Status**: ✅ done
- **Артефакты**: `AdvancedPanel.tsx`, `CollapsibleSection` badge
- DoD: collapsed default; MOEX cache + universe + recommendations внутри; «Опционально»

| Задача | Статус |
|--------|--------|
| T5.1 AdvancedPanel | ✅ |
| T5.2 MOEX cache | ✅ |
| T5.3 Universe LIVE | ✅ |
| T5.4 Recommendations | ✅ |
| T5.5 Settings без регрессии | ✅ |



---



## T6 — Cutover и приёмка

### T6.1 — Feature flip (default refactored)
- **Status**: ✅ done
- **Артефакты**: `featureFlag.ts`, `TestingPage.tsx`, `App.tsx` redirect
- DoD: `/testing` → refactored по умолчанию; legacy через `VITE_TESTING_LEGACY=true`

| Задача | Статус |
|--------|--------|
| T6.1 Feature flip | ✅ |
| T6.2–T6.4 E2E / regression | 🔲 manual (§9 чеклист) |
| T6.5 Документация | ✅ |
| T6.6 Deprecate legacy | ✅ |
| T6.7 Чеклист + status | ✅ |



---



## Сводка прогресса

| Release | Статус | Прогресс |
|---------|--------|----------|
| T0 Backend | 🟡 | 6/8 done, 2 partial |
| T1 Foundation | ✅ | 8/8 |
| T2 Setup UI | ✅ | 10/10 |
| T3 Run UI | ✅ | 7/7 |
| T4 Analysis | ✅ | 7/7 |
| T5 Advanced | ✅ | 5/5 |
| T6 Cutover | 🟡 | 4/7 code done; E2E manual pending |

**Следующий шаг:** ручной прогон §9 E2E (MOEX + Crypto) на вашем окружении с токенами.



---



*При завершении задачи: менять Status, отмечать DoD, обновлять ACCEPTANCE-CHECKLIST.*

