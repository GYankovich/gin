---
name: trading-metrics-calculation
description: >-
  Defines mandatory trading performance metrics and how to state them in BRDs
  and strategy memos. Use whenever calculating or reporting Sharpe, drawdown,
  win rate, or related MOEX strategy KPIs.
---

# Trading metrics (always include)

For any strategy or backtest **business** discussion, provide a **Metrics** subsection with **numeric targets or historical estimates** and **definitions**. Use annualized figures where the horizon ≥ 1y; otherwise label the horizon explicitly.

## Required metrics block (template)

Copy and fill:

```markdown
## Metrics

| Metric | Definition (one line) | Target / estimate | Notes |
|--------|------------------------|-------------------|--------|
| CAGR or period return | … | … | Horizon: … |
| Volatility (ann.) | Std dev of returns × √252 (daily) | … | MOEX session vs 24h if relevant |
| Sharpe (ann.) | (R − Rf) / σ; state Rf (often 0 for rough BRD) | … | |
| Max drawdown | Peak-to-trough on equity curve | … % | Duration of DD if known |
| Calmar | CAGR / |max DD| | … | Optional if horizon clear |
| Win rate | Winning periods / total (define period: trade, day, week) | … | |
| Avg win / avg loss | Mean PnL winners / |mean PnL losers| | … | |
| Exposure | Avg % gross/net invested | … | |
| Turnover | Annualized traded notional / NAV | … | Impacts costs |

### Costs (qualitative + order of magnitude)
- Commission model (broker tier if known), taxes where relevant
- Expected slippage (bps) for liquid vs illiquid names

### Benchmark
- State comparator (e.g. IMOEX, sector ETF proxy) and **expected alpha** or tracking error if applicable.
```

## Rules

1. If data is unknown, give a **range** and list **what data** would pin it down (e.g. daily OHLC from T-Investments `GetCandles`).
2. Never present a single return number without **max DD** alongside for risk strategies.
3. For MOEX, mention **RUB PnL** vs **currency** if FX hedging is in scope.
