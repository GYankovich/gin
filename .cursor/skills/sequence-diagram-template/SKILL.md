---
name: sequence-diagram-template
description: >-
  Mermaid sequence diagram patterns for order placement, data refresh, and
  backtest runs. Use when documenting request/response flows across services.
---

# Sequence diagrams (Mermaid)

Use for multi-party flows (client, API, broker adapter, DB, queue). Annotate lifelines with `[ref: BRD-XX]` where the BRD defines the step.

## Template

```mermaid
sequenceDiagram
  autonumber
  participant C as Client [ref: BRD-XX]
  participant API as REST API [ref: BRD-XX]
  participant AD as Broker adapter [ref: BRD-XX]
  participant EXT as T-Investments / MOEX
  participant DB as PostgreSQL [ref: BRD-XX]

  C->>API: Request (idempotent key)
  API->>DB: Persist intent / state
  API->>AD: Execute
  AD->>EXT: Vendor call
  EXT-->>AD: Ack / reject
  AD-->>API: Normalized result
  API->>DB: Final state
  API-->>C: Response + error code mapping
```

## Conventions

- Show **timeouts** and **retries** as `alt` / `opt` blocks when specified in BRD
- Show **429** / rate-limit path explicitly if integration is rate-limited
- Use **parallel** `par` blocks only when ordering is guaranteed irrelevant

## Backtest-specific fragment

```mermaid
sequenceDiagram
  participant O as Orchestrator [ref: BRD-XX]
  participant E as Engine [ref: BRD-XX]
  participant S as Candle source [ref: BRD-XX]
  O->>S: Load range
  S-->>E: Iterator / batch
  loop each timestep
    E->>E: Strategy + fills
  end
  O->>O: Persist metrics
```
