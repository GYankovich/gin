---
name: multi-tenant-trading
description: >-
  Multi-tenant and concurrency checklist for trading backends: isolation,
  token scopes, rate limits, and conflicting writes. Use when architecture
  spans multiple users or robots.
---

# Multi-tenant trading conflicts

Add a **Conflicts and mitigations** subsection to architecture docs. Map each item to `[ref: BRD-XX]` when the BRD defines tenancy or roles.

## Isolation

- **Data**: row-level tenant key (`user_id`, `org_id`); separate schemas only if BRD requires hard isolation
- **Secrets**: API tokens per tenant; no shared broker credentials unless explicitly allowed
- **WebSocket**: channel namespacing; avoid cross-tenant fan-out leaks

## Rate limits and quotas

- Map **T-Investments** and **MOEX** limits per token/account; specify **global vs per-robot** throttles
- Define **429** handling: queue, shed load, or delay — and whether idempotent retries are safe

## Concurrency

- **Orders**: single-writer per account or optimistic concurrency (`version` / `updated_at`)
- **Schedulers**: distributed lock or lease table for overlapping cron windows
- **Backtests**: CPU/memory isolation (worker pools per tenant) if SaaS

## Checklist (copy into ARCH doc)

```markdown
- [ ] Tenant key on all mutable tables [ref: BRD-XX]
- [ ] Token scope documented per endpoint [ref: BRD-XX]
- [ ] Rate-limit budget split documented [ref: BRD-XX]
- [ ] Order idempotency keys specified [ref: BRD-XX]
- [ ] WS authZ prevents cross-tenant subscriptions [ref: BRD-XX]
```
