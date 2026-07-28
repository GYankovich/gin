---
name: logging-standards
description: >-
  Structured logging and observability contract for trading services:
  correlation, PII, levels, and metrics hooks. Use when specifying logging in
  architecture or API docs.
---

# Logging standards (technical spec)

## Correlation

- Require **`correlation_id`** (or trace id) on REST and WS; propagate to broker adapter calls
- Log **order id / vendor order id** when BRD allows (no raw tokens)

## Fields (minimum contract)

| Field | Type | Example |
|-------|------|---------|
| timestamp | RFC3339 UTC | |
| level | enum | DEBUG…ERROR |
| service | string | `trading-api` |
| correlation_id | string | |
| event | string | `order.submit` |
| duration_ms | number | optional |
| error.code | string | on failures |

## Safety

- **Never** log secrets, refresh tokens, or full JWT
- **PII**: only per BRD; default to user opaque id

## Storage / retention

- Define **log sink** (stdout, file, vendor), **retention**, and **query path** (e.g. Loki, CloudWatch)
- Align **audit logs** (compliance) vs **debug logs** (short TTL)

## Metrics (optional cross-link)

- Counters: orders submitted, fills, vendor errors
- Histograms: vendor latency — reference in SLO subsection `[ref: BRD-XX]`
