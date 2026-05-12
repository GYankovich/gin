---
name: backtest-vectorized-template
description: >-
  Vectorized and batch-oriented backtest implementation patterns (OHLCV tables,
  alignment, costs, metrics) for Python trading backends. Use when implementing
  or refactoring historical simulation that precomputes signals on bar matrices
  rather than tick-by-tick event loops.
---

# Vectorized backtest template

## When to use

- Universe + calendar aligned on **bucket_start** (UTC).
- Strategy logic expressible on **arrays or frames** per step or full history (with look-ahead guards).

## Data contract

- Input: columns at minimum `open`, `high`, `low`, `close`, `volume`, `time` / `bucket_start`; instrument key (`figi` or internal id).
- All timestamps **UTC**; document interval (`1d`, `1h`, …).
- **No look-ahead**: signals for bar `t` may use only data `<= t` (inclusive close vs next open—state explicitly).

## Pipeline shape

1. **Load** candles (DB or service) → sort by time.
2. **Features** — numpy / polars / pandas; keep dtypes explicit for mypy-friendly helpers.
3. **Positions** — vectorized weights or event list → **validate** constraints (max leverage, integer lots if required).
4. **Costs** — reuse project `TradingCosts` / `resolve_robot_cost_rates` from `app.modules.robots.trading.costs` when simulating this codebase.
5. **Metrics** — equity curve, drawdown, Sharpe (document assumptions); align with `skill://trading-metrics-calculation` for reporting text.

## Integration in this repo

- Reference implementation and orchestration: `backend/app/modules/robots/trading/backtest/engine.py` and siblings (`broker_emulator.py`, `virtual_portfolio.py`, `sim_executor.py`, `metrics.py`).
- Business scope inputs: `skill://backtest-requirements-template`.

## Checklist

- [ ] Pydantic models for any HTTP/API payload for running a backtest; no raw `dict` at boundaries.
- [ ] Deterministic run (seed, stable sort, fixed costs).
- [ ] Tests: small synthetic OHLCV where hand-calculable PnL is known.
