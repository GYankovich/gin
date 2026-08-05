#!/usr/bin/env python3
"""Inspect backtest run and background_jobs queue."""
from __future__ import annotations

import sys
from sqlalchemy import text
from app.core.database import SessionLocal
from app.core.config import settings

run_id = int(sys.argv[1]) if len(sys.argv) > 1 else 142

db = SessionLocal()
try:
    schema = settings.DB_SCHEMA
    r = db.execute(
        text(
            f"""
            SELECT id, status, run_phase, progress_percent, started_at,
                   cancel_requested, error_message, user_id, robot_id
            FROM backtest_runs WHERE id = :rid
            """
        ),
        {"rid": run_id}
    ).mappings().first()
    print("backtest_run:", dict(r) if r else None)

    jobs = db.execute(
        text(
            f"""
            SELECT id, lane, job_type, status, created_at, started_at,
                   finished_at, error, message, idempotency_key, payload
            FROM background_jobs
            WHERE idempotency_key = :ik
               OR payload::text LIKE :pat
            ORDER BY created_at DESC
            LIMIT 5
            """
        ),
        {"ik": f"history_backtest:{run_id}", "pat": f"%\"run_id\": {run_id}%"}
    ).mappings().all()
    print("related_jobs:")
    for j in jobs:
        d = dict(j)
        d.pop("payload", None)
        print(" ", d)

    queued = db.execute(
        text(
            f"""
            SELECT id, lane, job_type, status, created_at
            FROM background_jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 20
            """
        )
    ).mappings().all()
    print("queued_jobs:", [dict(x) for x in queued])
    print("WORKER_EMBEDDED_ENABLED:", settings.WORKER_EMBEDDED_ENABLED)
finally:
    db.close()
