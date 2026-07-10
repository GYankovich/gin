---
name: c4-model-template
description: >-
  C4 model Mermaid templates (system context, containers, components) for
  trading platforms. Use when the user or systems-analyst agent needs
  architecture diagrams or component boundaries.
---

# C4 model (Mermaid)

Use **at least one** of the levels below per architecture doc. Label every box or boundary with `[ref: BRD-XX]` where applicable.

Prefer **flowchart** blocks for compatibility (default Mermaid). Use **C4Context** only if the target renderer loads the C4 plugin.

## System context (portable)

```mermaid
flowchart TB
  U[Trader / Ops] --> S["Trading platform [ref: BRD-XX]"]
  S --> MOEX[MOEX ISS]
  S --> TINV[T-Investments API]
```

## System context (C4 plugin optional)

```mermaid
C4Context
title System context — <system name>
Person(user, "Trader / Ops", "Uses the platform")
System(sys, "<System name>", "One-line purpose [ref: BRD-XX]")
System_Ext(moex, "MOEX ISS", "Market reference data")
System_Ext(tinv, "T-Investments API", "Orders, portfolio, streaming")
Rel(user, sys, "HTTPS / WS")
Rel(sys, moex, "HTTPS")
Rel(sys, tinv, "HTTPS / gRPC / WS")
```

## Containers

```mermaid
flowchart TB
  subgraph clients["Clients [ref: BRD-XX]"]
    WEB[Web UI]
    API_CLIENT[API clients]
  end
  subgraph backend["Backend [ref: BRD-XX]"]
    API[REST API]
    WS[WebSocket gateway]
    WORK[Workers / schedulers]
  end
  subgraph data["Data [ref: BRD-XX]"]
    DB[(PostgreSQL)]
    TS[(Time-series / candles store)]
    MQ{{Queue / stream}}
  end
  WEB --> API
  WEB --> WS
  API_CLIENT --> API
  API --> DB
  WORK --> MQ
  WORK --> TS
```

## Components (example slice)

```mermaid
flowchart LR
  R[Router layer] --> S[Domain services]
  S --> Q[Queries / repositories]
  Q --> DB[(DB)]
  S --> EXT[External API adapters]
```

Keep diagrams readable: ≤15 nodes per diagram; split into multiple figures if needed.
