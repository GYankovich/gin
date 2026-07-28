"""DB leases for standalone/embedded lane workers (one active process per lane)."""

from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

Schema = settings.DB_SCHEMA


class WorkerLeaseConflictError(RuntimeError):
    def __init__(self, *, lane: str, holder: Dict[str, Any]):
        self.lane = lane
        self.holder = holder or {}
        host = self.holder.get("hostname") or "?"
        pid = self.holder.get("pid") or "?"
        hb = self.holder.get("heartbeat_at") or "?"
        super().__init__(
            f"Worker lane={lane!r} already active on {host} pid={pid} "
            f"(heartbeat_at={hb}). Stop it or pass --force-lease."
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_active_worker_lease(db: Session, *, lane: str) -> Optional[Dict[str, Any]]:
    """Return running lease for lane if heartbeat is still fresh."""
    stale_sec = int(getattr(settings, "WORKER_LEASE_STALE_SECONDS", 90) or 90)
    row = db.execute(
        text(f"""
            SELECT lane, worker_id, hostname, pid, status, started_at, heartbeat_at
            FROM {Schema}.background_worker_leases
            WHERE lane = :lane
              AND status = 'running'
              AND heartbeat_at >= :fresh_after
            LIMIT 1
        """),
        {
            "lane": str(lane),
            "fresh_after": _now() - timedelta(seconds=max(15, stale_sec)),
        },
    ).mappings().first()
    return dict(row) if row else None


def try_acquire_worker_lease(
    db: Session,
    *,
    lane: str,
    force: bool = False,
    worker_id: Optional[UUID] = None,
    hostname: Optional[str] = None,
    pid: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Acquire exclusive lease for lane.
    Raises WorkerLeaseConflictError if another fresh worker holds it (unless force).
    """
    wid = worker_id or uuid4()
    host = hostname or socket.gethostname()
    process_id = int(pid if pid is not None else os.getpid())
    stale_sec = int(getattr(settings, "WORKER_LEASE_STALE_SECONDS", 90) or 90)
    fresh_after = _now() - timedelta(seconds=max(15, stale_sec))
    now = _now()

    # Serialize acquire per lane across processes.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": f"bg_worker_lease:{lane}"},
    )

    # Lock row (or absence) for this lane.
    existing = db.execute(
        text(f"""
            SELECT lane, worker_id, hostname, pid, status, started_at, heartbeat_at
            FROM {Schema}.background_worker_leases
            WHERE lane = :lane
            FOR UPDATE
        """),
        {"lane": str(lane)},
    ).mappings().first()

    if existing:
        st = str(existing.get("status") or "")
        hb = existing.get("heartbeat_at")
        is_fresh = st == "running" and hb is not None and hb >= fresh_after
        if is_fresh and not force and UUID(str(existing["worker_id"])) != wid:
            raise WorkerLeaseConflictError(
                lane=str(lane),
                holder={
                    "worker_id": str(existing["worker_id"]),
                    "hostname": existing.get("hostname"),
                    "pid": existing.get("pid"),
                    "heartbeat_at": existing.get("heartbeat_at"),
                    "started_at": existing.get("started_at"),
                },
            )
        db.execute(
            text(f"""
                UPDATE {Schema}.background_worker_leases
                SET worker_id = :wid,
                    hostname = :hostname,
                    pid = :pid,
                    status = 'running',
                    started_at = :now,
                    heartbeat_at = :now,
                    updated_at = :now
                WHERE lane = :lane
            """),
            {
                "lane": str(lane),
                "wid": wid,
                "hostname": host,
                "pid": process_id,
                "now": now,
            },
        )
    else:
        db.execute(
            text(f"""
                INSERT INTO {Schema}.background_worker_leases
                    (lane, worker_id, hostname, pid, status, started_at, heartbeat_at, updated_at)
                VALUES
                    (:lane, :wid, :hostname, :pid, 'running', :now, :now, :now)
            """),
            {
                "lane": str(lane),
                "wid": wid,
                "hostname": host,
                "pid": process_id,
                "now": now,
            },
        )

    return {
        "lane": str(lane),
        "worker_id": wid,
        "hostname": host,
        "pid": process_id,
        "status": "running",
        "started_at": now,
        "heartbeat_at": now,
    }


def touch_worker_lease(db: Session, *, lane: str, worker_id: UUID) -> bool:
    """Heartbeat; returns False if lease no longer owned."""
    result = db.execute(
        text(f"""
            UPDATE {Schema}.background_worker_leases
            SET heartbeat_at = :now,
                updated_at = :now
            WHERE lane = :lane
              AND worker_id = :wid
              AND status = 'running'
        """),
        {"lane": str(lane), "wid": worker_id, "now": _now()},
    )
    try:
        return int(result.rowcount or 0) > 0
    except Exception:
        return False


def release_worker_lease(db: Session, *, lane: str, worker_id: UUID) -> bool:
    result = db.execute(
        text(f"""
            UPDATE {Schema}.background_worker_leases
            SET status = 'stopped',
                updated_at = :now
            WHERE lane = :lane
              AND worker_id = :wid
              AND status = 'running'
        """),
        {"lane": str(lane), "wid": worker_id, "now": _now()},
    )
    try:
        return int(result.rowcount or 0) > 0
    except Exception:
        return False


__all__ = [
    "WorkerLeaseConflictError",
    "get_active_worker_lease",
    "release_worker_lease",
    "touch_worker_lease",
    "try_acquire_worker_lease",
]
