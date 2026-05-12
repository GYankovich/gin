---
name: postgres-async-patterns
description: >-
  PostgreSQL access patterns for FastAPI backends: sessions, transactions,
  repositories, and migrations (Alembic). Use when persisting trading, market,
  or backtest data—prefer aligning with existing project DB style first.
---

# PostgreSQL patterns (async-first guidance)

## Align with this repo first

- Current core session stack lives in `backend/app/core/database.py` (**sync** `Session` + `sessionmaker`). New code should **match the existing style** unless a migration to async SQLAlchemy 2.x is an explicit task.
- Migrations: `alembic/versions/`; keep revisions small and reversible.

## If introducing async SQLAlchemy

- Engine: `create_async_engine` + `async_sessionmaker`.
- **Session scope**: request-scoped `AsyncSession` via FastAPI `Depends`; `async with session.begin():` for transactions.
- **Repositories**: thin functions or classes; SQL in one place; return typed rows or Pydantic DTOs.

## Schema design

- Use `skill://time-series-storage-patterns` for candles, decisions, logs.
- Explicit `timestamptz`, `numeric` for money, bigint for quantities where integer lots matter.

## Safety

- No string-concatenated SQL; use bound parameters / SQLAlchemy expressions.
- Migrations must set indexes for FK and time-range queries declared in the spec.

## Checklist

- [ ] Indexes for hot paths `(tenant_or_robot_id, time DESC)` where applicable.
- [ ] Tests against real Postgres in CI or docker-compose when feasible; else SQLite only if schema-compatible.
