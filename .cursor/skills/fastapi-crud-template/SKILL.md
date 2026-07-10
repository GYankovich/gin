---
name: fastapi-crud-template
description: >-
  FastAPI module layout for CRUD-style REST: APIRouter, Pydantic v2 schemas,
  dependency-injected services, and OpenAPI-friendly errors. Use when adding or
  extending HTTP APIs in this backend.
---

# FastAPI CRUD template (this repository)

## Router layout

- One module per domain: `router.py`, `schemas.py`, `service.py`, `queries.py` (match `backend/app/modules/*/`).
- Register in `backend/app/main.py` with `app.include_router(..., prefix="/api", tags=[...])` unless the domain needs a dedicated sub-prefix (e.g. `/api/tinvest`).

## Patterns

- **Pydantic v2** for request/response models; use `model_config` / field validators as needed; no untyped `dict` in public signatures.
- **Dependencies**: `Depends(get_db)` or project-specific session/provider from `app.core.database` / modules.
- **HTTP errors**: use `HTTPException` with stable `detail` codes where the client branches; for expected domain failures prefer mapping to HTTP status + structured body (align with `app.core.exceptions` if used).
- **Async**: prefer `async def` handlers when I/O is async; if the stack is sync SQLAlchemy, keep handlers sync—**do not mix** unbounded thread offload without an explicit pattern.

## OpenAPI

- Meaningful `summary`, `response_model`, `tags`.
- Pagination: query `limit`/`offset` or cursor; cap `limit` server-side.

## Security

- Auth as in `app.modules.auth`; never log secrets; env-driven config via `app.core.config.settings`.

## Checklist

- [ ] Idempotency for **mutating** trading endpoints (header or body key) where spec requires it.
- [ ] Tests: `TestClient` or async client, fixtures for DB session.
- [ ] Structured logging with correlation (see `skill://logging-standards`).
