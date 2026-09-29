# ARCH-06: Общее торговое ядро (trading_core)

**Версия:** 0.2  
**Дата:** 2026-09-29  
**Статус:** as-built (волны 1–4 в коде; wave 5 leftovers через shim)  
**Связь:** `[ref: ARCH-05]`, `[ref: BRD-ARCH-03]`

---

## 1. Зачем

Одни правила рынка для **живых роботов** и **бэктеста/оптимизации**:
свечи, позиции, сигналы, заявки, интервалы, комиссии.

Робот решает *когда* торговать; ядро задаёт *как считать и исполнять*.

## 2. Границы

| В ядре | Не в ядре |
|--------|-----------|
| Контракты данных, интервалы, комиссии | UI, RobotService, джобы вселенной |
| Риск, брокеры, market data, sim/logging | Стратегии grain_seed / session orchestration |
| | Отбор universe (отдельный шаг) |

**Правило:** `trading_core` не импортирует `robots` / `robots_v2`.

**Prod path:** UI `/robots` → `/api/v2/robots` → `robots_v2` (+ `trading_core`). Legacy v1 HTTP unmounted.

## 3. Волны

| Волна | Содержание | Статус |
|-------|------------|--------|
| **1** | contracts, intervals, costs | ✅ |
| **2** | risk (params, manager) | ✅ |
| **3** | brokers + position sync | ✅ |
| **4** | market data (cache / facade / prefetch) | ✅ |
| **5** | sim / logging leftovers | ✅ as-built (canonical in `trading_core.sim` / `trading_core.logging`; shims under `robots.trading.backtest`) |

## 4. Совместимость

Старые пути `app.modules.robots.trading.{contracts,intervals,costs,brokers,risk,data,...}` —
тонкие shim’ы на `trading_core`. Новый код (`robots_v2`) импортирует `trading_core` напрямую.

History-backtest monolith (`engine.py`, `unified_runner`, `history_backtest_robot`) **удалён**.
Prod backtest: `robots_v2.backtest` + job `backtest_run`.

## Changelog

| Ver | Date | Notes |
|-----|------|-------|
| 0.2 | 2026-09-29 | As-built: waves 2–5 landed; cutover note |
| 0.1 | 2026-09-29 | Волна 1: пакет `trading_core` + shims |
