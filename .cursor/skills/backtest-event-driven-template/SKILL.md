---
name: backtest-event-driven-template
description: >-
  Event-driven backtest patterns: ordered timeline of market and broker events,
  fill simulation, partial fills, and session rules. Use when bar-close
  vectorization is insufficient (intraday path, queue position, latency models).
---

# Event-driven backtest template

## When to use

- **Intraday** or mixed event types (quotes, trades, depth).
- Explicit **latency**, **slippage**, or **order book** abstraction.
- **Broker state machine**: submit → ack → partial fill → cancel.

## Event types (minimal)

| Event | Fields (conceptual) |
|-------|---------------------|
| `BAR` | instrument, interval, OHLCV, time |
| `TICK` | price, size, side, time |
| `ORDER_SUBMIT` | client_order_id, idempotency_key, side, qty, type, limit_price |
| `ORDER_ACK` / `REJECT` | reason code |
| `FILL` | qty, price, fee |

## Loop

1. Push events onto a **priority queue** by `time` then stable tie-break.
2. Strategy reads **observable** state only (no future events).
3. **Clock**: same monotonic rules as live trading session (timezone + session calendar in BRD).

## Idempotency

- Every simulated `ORDER_SUBMIT` carries **idempotency_key**; duplicate event → no double position.

## Integration in this repo

- Prefer composing with existing backtest modules under `backend/app/modules/robots/trading/backtest/`; extend rather than fork `engine.py` unless the event model diverges strongly.
- For storage of runs and artifacts, follow Alembic models already used for backtests in this project.

## Checklist

- [ ] Property-based or table-driven tests for ordering of simultaneous events.
- [ ] Document divergence from vectorized assumptions in module docstring.
