---
name: risk-assessment-checklist
description: >-
  Risk checklist for Russian equities and T-Investments execution. Use for any
  strategy BRD, portfolio review, or go/no-go before implementation handoff.
---

# Risk assessment checklist

Always add a section **Risk assessment** using the checklist below. For each item: **status** (Low / Medium / High), **evidence or reasoning**, **mitigation** (business-level, not code).

## 1. Market and liquidity

- [ ] Name concentration vs MOEX depth (ADV, top-of-book size)
- [ ] Gap / auction risk (overnight, news, sanctions headlines)
- [ ] Sector / factor crowding (e.g. banks, exporters vs RUB)

## 2. Execution

- [ ] Slippage vs intended style (marketable limits, IOC, spread)
- [ ] **T-Investments API**: rate limits, retries, partial fills, session vs OTC
- [ ] Latency: signal freshness vs REST polling / WebSocket stream

## 3. Model and data

- [ ] Survivorship / universe bias in historical view
- [ ] Corporate actions (dividends, splits, delistings)
- [ ] Bad or missing candles; timezone (MSK vs UTC) alignment

## 4. Portfolio risk

- [ ] Correlation under stress (RUB down, oil shock, rates up)
- [ ] Tail dependence (single-factor exposure)
- [ ] Leverage / margin (if applicable): call risk, funding

## 5. Operational

- [ ] Key person / manual steps
- [ ] Broker or token outage; failover expectation

## Output format

```markdown
## Risk assessment

| # | Risk area | Severity | Summary | Mitigation |
|---|-----------|----------|---------|------------|
| 1 | … | L/M/H | … | … |
...
```

Close with **Residual risks** (what cannot be fully mitigated at BRD stage).
