---
name: backtest-requirements-template
description: >-
  Business requirements template for backtests of MOEX strategies using
  T-Investments-sourced data. Use when defining what to simulate before any
  implementation work.
---

# Backtest requirements (BRD fragment)

Use this inside or alongside `docs/BRD-XX-description.md` when backtesting is in scope.

```markdown
## Backtest requirements

### Scope
- Strategy name and version
- Universe rules (liquidity, price, listing, sector exclusions)
- Date range (train / validation / hold-out if applicable)

### Data (T-Investments)
- Bar interval(s) required (e.g. `CANDLE_INTERVAL_DAY`, hour, minute)
- Fields needed (OHLCV, trades, order book depth if ever required—note API limits)
- Corporate action handling expectation (adjust vs cash)
- Benchmark series for comparison

### Simulation assumptions
- Transaction costs: commission (bps), slippage model (fixed bps vs spread fraction)
- Fill model assumption (mid, close, realistic spread for MOEX names)
- Position sizing rule as implementable rules (fixed %, volatility targeting)

### Outputs required from backtest
- Equity curve, drawdown series
- Table of metrics (see `trading-metrics-calculation`)
- Trade list statistics (count, avg hold, win rate)

### Acceptance criteria
- Minimum Sharpe / max DD thresholds for “pass”
- Sensitivity cases (e.g. costs +50%, slippage doubled)

### Out of scope / limitations
- What will **not** be modeled (e.g. market impact for huge size)
```

Cross-reference **t-investments-market-data-guide** for concrete API alignment.
