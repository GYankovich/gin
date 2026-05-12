---
name: t-investments-client-implementation
description: >-
  Implementation guide for T-Invest (T-Bank) Invest API clients in Python:
  REST, optional gRPC SDK, WebSocket streaming, tokens, and sandbox vs prod.
  Use when writing or refactoring execution and market-data code—not BRD-only
  data summaries.
---

# T-Investments client implementation

## BRD / data reference

- Analyst-facing data surfaces: `skill://t-investments-market-data-guide`.

## Implementation rules

- **Secrets**: token from env / settings only (`app.core.config`); never log token values.
- **FIGI**: resolve via shared `InstrumentsClient` patterns under `backend/app/modules/tinvest/methods/`; cache responsibly.
- **REST base URL**: align with deployment (`invest-public-api.tbank.ru` in this project’s facade patterns).
- **WebSocket**: reconnect with backoff; treat stream as **best-effort**; persist snapshots if the strategy requires recovery.

## Orders

- **Idempotency key** on every submit/replace/cancel where the broker supports it; store and dedupe server-side for robot retries.
- Map API errors to typed **Result** or domain errors per senior backend agent rules; unexpected failures may still use exceptions at HTTP boundary.

## Rate limits

- Use `skill://async-rate-limiter`; see `backend/app/modules/robots/trading/brokers/rate_limiter.py` for sliding-window pattern in this repo.

## Testing

- Mock HTTP/SDK at the transport layer; contract tests for critical JSON shapes with golden files.

## Entry points in this repo

- `backend/app/modules/tinvest/facade.py`, `router.py`, `methods/` — follow existing structure when adding calls.
