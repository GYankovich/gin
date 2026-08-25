"""PostgreSQL queue for background_jobs (SKIP LOCKED per lane)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

Schema = settings.DB_SCHEMA


def _json_payload(payload: Dict[str, Any]) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, default=str)


def has_active_job(db: Session, *, idempotency_key: str) -> bool:
    if not idempotency_key:
        return False
    row = db.execute(
        text(f"""
            SELECT 1
            FROM background_jobs
            WHERE idempotency_key = :ik
              AND status IN ('queued', 'running')
            LIMIT 1
        """),
        {"ik": idempotency_key[:160]}
    ).first()
    return row is not None


def find_latest_job_for_robot(
    db: Session,
    *,
    job_type: str,
    robot_id: int,
    statuses: Optional[tuple] = None
) -> Optional[Dict[str, Any]]:
    """Latest background_jobs row for robot_id in payload (optionally filtered by status)."""
    params: Dict[str, Any] = {
        "job_type": str(job_type),
        "rid": str(int(robot_id)),
    }
    status_clause = ""
    if statuses:
        parts = []
        for i, st in enumerate(statuses):
            key = f"st{i}"
            parts.append(f":{key}")
            params[key] = str(st)
        status_clause = f"AND status IN ({', '.join(parts)})"
    row = db.execute(
        text(f"""
            SELECT id, lane, job_type, status, created_at, started_at, finished_at,
                   error, message, payload
            FROM background_jobs
            WHERE job_type = :job_type
              AND (payload->>'robot_id') = :rid
              {status_clause}
            ORDER BY created_at DESC
            LIMIT 1
        """),
        params
    ).mappings().first()
    return dict(row) if row else None


def find_background_job_for_backtest_run(db: Session, run_id: int) -> Optional[Dict[str, Any]]:
    """Latest background_jobs row for history_backtest run_id (any status)."""
    ik = f"history_backtest:{int(run_id)}"
    row = db.execute(
        text(f"""
            SELECT id, lane, job_type, status, created_at, started_at, finished_at, error, message
            FROM background_jobs
            WHERE idempotency_key = :ik
               OR payload->>'run_id' = :rid
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"ik": ik, "rid": str(int(run_id))}
    ).mappings().first()
    return dict(row) if row else None


def enqueue_background_job(
    db: Session,
    *,
    lane: str,
    job_type: str,
    payload: Dict[str, Any],
    idempotency_key: Optional[str] = None,
    priority: int = 0,
    run_after: Optional[datetime] = None
) -> Optional[UUID]:
    """Insert job; returns None if idempotency_key already has queued/running job."""
    ik = (idempotency_key or "")[:160] or None
    if ik and has_active_job(db, idempotency_key=ik):
        return None

    row = db.execute(
        text(f"""
            INSERT INTO background_jobs
                (lane, job_type, status, priority, payload, idempotency_key, run_after)
            VALUES
                (:lane, :job_type, 'queued', :priority, CAST(:payload AS jsonb), :ik, :run_after)
            RETURNING id
        """),
        {
            "lane": lane,
            "job_type": job_type,
            "priority": int(priority),
            "payload": _json_payload(payload),
            "ik": ik,
            "run_after": run_after,
        }
    ).scalar()
    return row


def claim_next_background_job(db: Session, *, lane: str) -> Optional[Dict[str, Any]]:
    row = db.execute(
        text(f"""
            WITH c AS (
                SELECT id
                FROM background_jobs
                WHERE lane = :lane
                  AND status = 'queued'
                  AND (run_after IS NULL OR run_after <= CURRENT_TIMESTAMP)
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE background_jobs j
            SET status = 'running',
                started_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                attempts = j.attempts + 1,
                message = 'running'
            FROM c
            WHERE j.id = c.id
            RETURNING j.id, j.lane, j.job_type, j.payload, j.attempts, j.idempotency_key
        """),
        {"lane": lane}
    ).mappings().first()
    if not row:
        return None
    out = dict(row)
    payload = out.get("payload")
    if isinstance(payload, str):
        out["payload"] = json.loads(payload)
    return out


def complete_background_job(
    db: Session,
    job_id: UUID,
    *,
    message: Optional[str] = None
) -> None:
    db.execute(
        text(f"""
            UPDATE background_jobs
            SET status = 'done',
                message = COALESCE(:message, message),
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """),
        {"id": job_id, "message": message}
    )


def fail_background_job(
    db: Session,
    job_id: UUID,
    error: str,
    *,
    message: Optional[str] = None
) -> None:
    db.execute(
        text(f"""
            UPDATE background_jobs
            SET status = 'failed',
                error = :error,
                message = COALESCE(:message, 'failed'),
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """),
        {"id": job_id, "error": str(error)[:4000], "message": message}
    )


def cancel_live_session_jobs_for_robot(
    db: Session,
    *,
    robot_id: int,
    reason: str = "robot disabled"
) -> int:
    """
    Stop signal for live: mark queued/running live_trading_session jobs for robot as failed.
    Running session must also poll robots.status and exit cooperatively.
    """
    result = db.execute(
        text(f"""
            UPDATE background_jobs
            SET status = 'failed',
                error = :error,
                message = :message,
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_type = 'live_trading_session'
              AND status IN ('queued', 'running')
              AND (payload->>'robot_id') = :rid
        """),
        {
            "rid": str(int(robot_id)),
            "error": str(reason)[:4000],
            "message": "cancelled (robot status off)",
        }
    )
    try:
        return int(result.rowcount or 0)
    except Exception:
        return 0


def touch_background_job(db: Session, job_id: UUID) -> None:
    """Heartbeat: keep long-running jobs from looking stale."""
    db.execute(
        text(f"""
            UPDATE background_jobs
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
              AND status = 'running'
        """),
        {"id": job_id}
    )


def fail_stale_queued_portfolio_jobs(db: Session, *, stale_seconds: int) -> int:
    """Fail portfolio_sync jobs stuck in queued (dead worker blocks idempotency key)."""
    if stale_seconds <= 0:
        return 0
    row = db.execute(
        text(f"""
            UPDATE background_jobs
            SET status = 'failed',
                error = COALESCE(error, 'stale queued portfolio_sync'),
                message = 'failed (stale queued)',
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'queued'
              AND job_type = 'portfolio_sync'
              AND created_at < (CURRENT_TIMESTAMP - make_interval(secs => :stale_seconds))
        """),
        {"stale_seconds": int(stale_seconds)},
    )
    return int(row.rowcount or 0)


def fail_stale_background_jobs(db: Session, *, stale_seconds: int) -> int:
    """Fail short-lived jobs stuck in running.

    Long-running ``live_trading_session`` jobs use heartbeat +
    ``fail_stale_live_session_jobs`` instead of this timeout.
    """
    if stale_seconds <= 0:
        return 0
    row = db.execute(
        text(f"""
            UPDATE background_jobs
            SET status = 'failed',
                error = COALESCE(error, 'stale running job timeout'),
                message = 'failed (stale timeout)',
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'running'
              AND job_type NOT IN ('live_trading_session')
              AND updated_at < (CURRENT_TIMESTAMP - make_interval(secs => :stale_seconds))
        """),
        {"stale_seconds": int(stale_seconds)}
    )
    return int(row.rowcount or 0)


def fail_stale_live_session_jobs(db: Session, *, stale_seconds: int) -> int:
    """Fail live sessions that stopped heartbeating (process crash / hung task)."""
    if stale_seconds <= 0:
        return 0
    row = db.execute(
        text(f"""
            UPDATE background_jobs
            SET status = 'failed',
                error = COALESCE(error, 'stale live session (no heartbeat)'),
                message = 'failed (live session stale)',
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'running'
              AND job_type = 'live_trading_session'
              AND updated_at < (CURRENT_TIMESTAMP - make_interval(secs => :stale_seconds))
        """),
        {"stale_seconds": int(stale_seconds)}
    )
    return int(row.rowcount or 0)


def fail_orphaned_live_session_jobs(db: Session, *, lane: Optional[str] = None) -> int:
    """Mark live_trading_session jobs left in running after worker/process restart."""
    lane_clause = "AND lane = :lane" if lane else ""
    params: Dict[str, Any] = {}
    if lane:
        params["lane"] = lane
    row = db.execute(
        text(f"""
            UPDATE background_jobs
            SET status = 'failed',
                error = COALESCE(error, 'orphaned live session after worker restart'),
                message = 'failed (orphan reset on worker start)',
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'running'
              AND job_type = 'live_trading_session'
              {lane_clause}
        """),
        params
    )
    return int(row.rowcount or 0)
