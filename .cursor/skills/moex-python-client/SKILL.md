---
name: moex-python-client
description: >-
  MOEX ISS–oriented HTTP client patterns in Python (httpx/aiohttp), caching,
  error handling, and reference data concepts. Use when implementing or extending
  MOEX data fetchers—pair with moex-api-reference for URL semantics.
---

# MOEX Python client template

## Documentation skill

- URL semantics, boards, and caveats: `skill://moex-api-reference`.

## Client design

- **httpx.AsyncClient** or sync `httpx` consistent with the call site; set timeouts (`connect`, `read`, `write`, `pool`).
- **Base URL** from settings; no literals in business logic.
- **Retries**: only for idempotent GET; exponential backoff; respect `Retry-After` if present.
- **Parsing**: map JSON to **Pydantic v2** models at the boundary; inner code uses typed objects.

## Caching

- Short TTL in-memory or Redis (if project adds it) for static reference data; ETag if MOEX response supports conditional requests for your path.

## Rate limiting

- Coordinate with `skill://async-rate-limiter` for outbound bursts.

## Testing

- Mock `httpx` transport with recorded fixtures (`pytest`); include malformed payload test.

## This repo

- If MOEX code already exists under `backend/app/modules/`, extend it; otherwise place ISS client in a dedicated module (e.g. `app.modules.moex`) and wire through `facade`-style thin API if multiple callers.
