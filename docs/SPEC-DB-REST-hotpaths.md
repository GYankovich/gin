# SPEC-DB: REST hot paths — dashboard, portfolio, robot monitor

**Status:** In progress  
**Goal:** Stop recomputing day Δ / own_funds / ROI / W·L on every REST; serve from mart tables written at sync.

---

## Surfaces

| UI | Route | Hot REST |
|----|-------|----------|
| Dashboard | `/dashboard` | `POST /api/dashboard/data` |
| Portfolio | `/portfolio` | `GET /analytics/summary`, `POST /analytics/statistics_extended`, `POST /analytics/chart_series`, ops/snapshots |
| Monitor | `/robots/:id/monitor` | `GET /robots/{id}/status` (5–8s), audit (throttled) |

---

## Marts (tables, not SQL VIEW)

| Object | Grain | Written by | Read by |
|--------|-------|------------|---------|
| `portfolio_snapshot_daily` | account × Moscow day | `save_portfolio_snapshot` UPSERT | chart, period ROI/DD, fleet curve |
| `portfolio_account_stats` | account (1 row) | snapshot → total/dayΔ; ops sync → own_funds/FIFO W·L/ROI | dashboard, portfolio overall KPIs, fleet gain |
| `robot_day_stats` (phase S) | robot × Moscow day | `audit_persist_cycle` | fleet / monitor period; today = live + fills.pnl |

Postgres `CREATE VIEW` for own_funds/KPI is **out** (recomputes on every SELECT).

---

## Metric dictionary

1. **Own funds (lifetime)** — dashboard/fleet cashflow formula → `portfolio_account_stats.own_funds` (refresh on ops sync).
2. **Day Δ (account)** — daily today − yesterday close (or stats.day_over_day_*).
3. **ROI lifetime** — `(total − own_funds) / own_funds` from stats.
4. **Period ROI / drawdown / growth** — from daily series points in `[from, to]` (O(days)).
5. **W·L portfolio lifetime** — FIFO at ops sync → stats; period W·L → closed trades by `closed_at`.
6. **W·L robot** — `robot_fills.pnl` / `robot_day_stats`; not account FIFO.

---

## Period queries

- Chart / period ROI/DD: range scan `portfolio_snapshot_daily`.
- Overall cards: `portfolio_account_stats` (ignore period).
- Period W·L: filter closed trades / day_stats by date.
- Do **not** materialize every from–to combination.

---

## Phases checklist

- [x] **A** Monitor: throttle audit roundTrips/decisions off hot poll (60s + health/order)
- [x] **B** Dashboard: batch KPI SQL; prefer `portfolio_account_stats` when present
- [x] **S** `portfolio_account_stats` + daily TABLE + writers; `robot_day_stats` writer on cycle audit; backfill `0097`
- [x] **C** daily VIEW → TABLE; hourly clamp 14d; `portfolio_operations.ticker` denorm (`0097`)

---

## Monitor WS-first (follow-up)

- On `/robots/{id}/stream` connect: `type=snapshot` = robot + status + dayStats (`robot_day_stats`).
- Live deltas: `stage`, `cycle`, `positions`, `decision`, `universe`, `order` (+pnl), `day_stats`, `health` (state only).
- FE: no REST interval while WS connected; REST only on disconnect or 2.5s seed timeout; one-shot audit blotter after snapshot.

## Acceptance

- Page-load SQL count and latency for `/dashboard/data`, `/analytics/statistics_extended`, `/robots/audit` under RUNNING poll.
- KPI parity on 1–2 accounts / 1 robot vs baseline (S8).
- Monitor RUNNING: no periodic getStatus/audit while stream connected.
