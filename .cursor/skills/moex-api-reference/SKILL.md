---
name: moex-api-reference
description: >-
  MOEX ISS and related reference data concepts for architecture specs: common
  boards, query parameters, and integration caveats. Use when specifying MOEX
  data sources.
---

# MOEX data sources (architecture notes)

Use with `[ref: BRD-XX]` when the BRD names instruments, boards, or refresh cadence.

## MOEX ISS (informational web service)

- Typical use: **reference** listings, **history** for charts, **engines/markets** metadata
- Access: HTTPS; respect **robots / fair use** and **caching** in specs (ETag, conditional requests)
- Parameters often include `iss.json=extended`, `from`, `till`, `interval`, `start`, `limit`
- Specify in contracts: **ticker vs SECID** resolution, **timezone** (MSK vs UTC storage), **session calendar** (weekends, holidays)

## What to document in every integration spec

| Item | Spec detail |
|------|-------------|
| Dataset | e.g. history, securities, marketdata |
| Identifier | ticker, SECID, ISIN mapping strategy |
| Throttling | client-side QPS, backoff, jitter |
| Failure modes | partial pages, empty sets, stale ETag |
| Persistence | raw JSON vs normalized tables |

## Conflict notes

- ISS is **not** a low-latency execution feed; do not specify it for sub-second trading without `[NEEDS INPUT: alternative feed]`

For T-Investments execution and streaming details, use `skill://t-investments-market-data-guide` alongside this skill.
