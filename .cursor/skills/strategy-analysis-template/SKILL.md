---
name: strategy-analysis-template
description: >-
  Markdown template for MOEX trading strategy business analysis. Use when
  analyzing or documenting any strategy, portfolio approach, or trade idea
  requiring structured narrative and acceptance-style requirements.
---

# Strategy analysis output template

Use this structure for every strategy description. Replace bracketed placeholders; omit sections only if truly not applicable (say N/A with one line why).

```markdown
# Strategy: [short name]

## 1. Executive summary
- Objective (return, risk budget, horizon)
- Universe (e.g. blue chips MOEX, sector, liquidity band)
- Edge hypothesis (1–3 sentences)

## 2. Market context (MOEX)
- Regime / macro hooks relevant to Russia (rates, FX, sanctions, dividends)
- Typical liquidity session notes (auction, main session)

## 3. Signal and rules (business level)
- Entry conditions (qualitative + measurable where possible)
- Exit conditions (take-profit, stop, time stop, corporate actions)
- Holding period and turnover expectations

## 4. Instruments
- Primary tickers (examples: SBER, LKOH, GMKN, …)
- Asset classes (equity, bond, fut, FX)
- What to avoid and why (illiquid names, gaps)

## 5. Position sizing and capital
- Max position % NAV per name / sector
- Max gross / net exposure
- Rebalancing cadence

## 6. Data and execution dependencies
- Which T-Investments API surfaces are required (see `t-investments-market-data-guide`)
- Latency tolerance and manual vs automated execution assumption

## 7. Success criteria (business)
- Target metrics (link to metrics section)
- Kill switches (drawdown, consecutive losses, correlation breakdown)

## 8. Open questions
- Assumptions needing validation
- Missing data or research
```

Always connect sections 6–7 to explicit T-Investments capabilities/limitations where data or orders are involved.
