# ADR: Robots Greenfield (v2)

**Статус:** accepted  
**Дата:** 2026-08-12  
**Спека:** [robots_greenfield_spec.md](./robots_greenfield_spec.md)

Документ фиксирует продуктовые и архитектурные решения для параллельного контура v2. Отменяет или уточняет отдельные пункты greenfield-спеки там, где указано явно.

---

## ADR-01 — Параллельный контур v2

**Решение:** новый API и UI живут параллельно v1 до полной замены.

| Аспект | v1 (as-is) | v2 (greenfield) |
|--------|------------|-----------------|
| API | `/api/robots/*` | `/api/v2/robots/*` |
| Таблица | `robots` (v2/v3 config) | **Отдельная** (`robots_v2` или эквивалент) |
| UI | `/robots`, `/live`, `/testing` (legacy) | `/robots-v2`, новый live-monitor |
| Feature flag | — | `ROBOTS_V2_ENABLED` |

Старые роботы в v2 UI — **read-only** (просмотр без редактирования и запуска через v2).

---

## ADR-02 — Единый движок live + backtest

**Решение:** Strategy Runtime, Risk Engine и Trading Engine — один pipeline для live и backtest.

- Backtest host: historical Market Data + SimBroker.
- Страница **`/testing`** переключается на **v2 API** (не ждём отдельного этапа).
- v1 backtest endpoints остаются до удаления контура.

---

## ADR-03 — Paper: виртуальный капитал per robot

**Переопределяет** greenfield §14 «per user pool».

**Решение:**

- У каждого paper-робота **изолированный** виртуальный счёт (`PaperLedger`: cash, positions, PnL).
- `virtualCapital` задаётся при **`POST /api/v2/robots/{id}/start`** (обязателен для paper).
- Значение можно **менять при каждом новом старте** (диалог перед start).
- Последнее значение сохраняется как default в UI (metadata робота), не как жёсткий лимит конфига.
- Paper и live ledger **никогда** не смешиваются.

**Live:** sizing от брокерского счёта; опциональный `allocatedCapital` в RiskConfig — reference cap для sizing.

```typescript
interface StartRequest {
  stopMode?: 'soft' | 'hard'       // для stop
  virtualCapital?: number          // обязателен для mode=paper
}
```

---

## ADR-04 — Scalper и WebSocket

**Решение:**

- WS-канал — **внутри Trading Engine** (отдельный stream per session).
- Live-monitor v2 подключается к этому каналу (не legacy `live_ws.py`).
- **Scalper** доступен только при `core.advancedMode === true` («Расширенный режим» на шаге 1).

---

## ADR-05 — Миграция и стратегии

**Решение:**

- v1 → v2 **только для новых** роботов; автоконвертация существующих — **нет**.
- Стратегии v1 **не мапим**; 4 архетипа (scalper, momentum, reversion, grid) — **с нуля**.

---

## ADR-06 — Universe: index и crypto benchmark

**Решение:**

| Режим | Источник |
|-------|----------|
| MOEX index | MOEX ISS + T-Invest instruments API + **собственный кэш** |
| Crypto index MVP | **Top-10 by volume** |

---

## ADR-07 — Live monitor (замена `/live` для v2)

**Решение:**

- Новый route для v2 (например `/robots-v2/{id}/monitor`).
- URL и POST v1 (`/live/*`, `/api/robots/*`) — **не трогаем**.

**Подключение — гибрид:**

```text
Initial load:  GET  /api/v2/robots/{id}/status   → snapshot
Realtime:      WS   /api/v2/robots/{id}/stream   → equity, signals, orders, fills, health
Fallback:      poll GET /status каждые 5–10s при обрыве WS
```

Scalper order-flow — тот же WS-канал Engine.

---

## ADR-08 — Config versioning

**Решение:** таблица `robot_config_history`:

```sql
CREATE TABLE robot_config_history (
  id         UUID PRIMARY KEY,
  robot_id   UUID NOT NULL,
  version    INT NOT NULL,
  config     JSONB NOT NULL,
  created_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

При изменении конфига — новая запись, `version++`. Rollback через админку / API.

---

## ADR-09 — Idempotency ордеров

**Решение:** ключ = **`OrderIntent.id`** (UUID, генерируется один раз при создании intent, persist в БД до финального статуса ордера).

---

## ADR-10 — Slippage guard (live)

**Решение:** **Limit fallback** (не deny, не ignore).

```text
IF mode === 'live' AND orderType === 'market':
  spreadPct = (ask - bid) / mid × 100
  IF spreadPct > risk.slippagePct:
    convert to LIMIT @ lastPrice ± slippagePct (buy: +slippage, sell: −slippage)
    log Decision: SLIPPAGE_LIMIT_FALLBACK
  ELSE:
    submit market as planned
```

Paper: симуляция slippage по модели (без limit fallback).

---

## ADR-11 — Account reconciliation

**Решение:** **брокер всегда source of truth** — без уровней WARNING/CRITICAL.

```text
Каждый цикл (live):
  brokerState = BrokerGateway.getAccount()
  IF local AccountBook != brokerState:
    overwrite local from broker
    log reconciliation diff (equity, positions)
    emit event account.reconciled
```

Halt по reconciliation **не делаем** в MVP — только sync + audit log.  
Исключение: если sync технически невозможен (broker API error) — PreFlight Gate блокирует цикл.

---

## ADR-12 — MVP scope (зафиксировано ранее)

| Область | MVP |
|---------|-----|
| Архетипы | Все 4 |
| Рынки | MOEX/T-Invest + Bybit |
| UI | 4-step wizard, fleet v2, dashboard + **equity curve** |
| Grid | Virtual levels, `maxPositionSizePct`, `stopLossOnLevel` |
| Screener drop | hold (default); strict via `exitOnDrop` |

---

## ADR-13 — Signal queue tie-breaker

При равном `strength`: сортировка `strength DESC`, затем `ticker ASC`.

---

## Связь с roadmap

Оценка с учётом ADR-01…02: **~50–55 дней** (2 разработчика).

| Этап | Deliverable |
|------|-------------|
| 0 | OpenAPI `/api/v2/robots/`, Pydantic v4 config, этот ADR |
| 1 | Universe Service: preview, resolve, index cache |
| 2 | Strategy Runtime: 4 plugins |
| 3 | Risk + Trading Engine (unified cycle) |
| 3b | Backtest host + `/testing` → v2 |
| 4 | UI wizard, fleet v2, monitor |
| 5 | Bybit parity, QA |

---

## Changelog

| Дата | Изменение |
|------|-----------|
| 2026-08-12 | Initial: ADR-01…13, Q1–Q11 closed |
