"""Auto-resume robots v2 trading sessions after API restart."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

SESSION_DESIRED_KEY = "sessionDesired"
DELETED_AT_KEY = "deletedAt"


def _parse_metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def robots_to_resume(db, *, schema: str) -> list[dict[str, Any]]:
    """
    Robots that should come back after API restart:
    - metadata.sessionDesired == 'running', or
    - legacy: open audit session (crash) and sessionDesired != 'stopped'.
    """
    rows = db.execute(
        text(f"""
            SELECT r.id, r.user_id, r.token_id, r.config, r.metadata
            FROM {schema}.robots_v2 r
            WHERE r.type = 2
              AND r.token_id IS NOT NULL
              AND COALESCE(r.metadata->>'{DELETED_AT_KEY}', '') = ''
              AND (
                COALESCE(r.metadata->>'{SESSION_DESIRED_KEY}', '') = 'running'
                OR (
                    COALESCE(r.metadata->>'{SESSION_DESIRED_KEY}', '') <> 'stopped'
                    AND EXISTS (
                        SELECT 1 FROM {schema}.robots_v2_sessions s
                        WHERE s.robot_id = r.id AND s.ended_at IS NULL
                    )
                )
              )
            ORDER BY r.id
        """),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        cfg = row.config if isinstance(row.config, dict) else json.loads(row.config or "{}")
        meta = _parse_metadata(row.metadata)
        out.append({
            "robot_id": int(row.id),
            "user_id": int(row.user_id),
            "token_id": int(row.token_id),
            "config": cfg,
            "metadata": meta,
        })
    return out


async def close_orphan_audit_sessions(robot_id: int, *, stop_reason: str = "api_restart") -> int:
    """Close audit rows left open when the process died without graceful shutdown."""
    from app.modules.robots_v2.engine.audit import AuditStore

    schema = getattr(settings, "DB_SCHEMA", None) or "public"

    def _run() -> int:
        store = AuditStore()
        try:
            rows = store._db.execute(
                text(f"""
                    SELECT id FROM {schema}.robots_v2_sessions
                    WHERE robot_id = :robot_id AND ended_at IS NULL
                """),
                {"robot_id": robot_id},
            ).fetchall()
            for row in rows:
                store.end_session(row[0], stop_reason=stop_reason)
            return len(rows)
        finally:
            store.close()

    return await asyncio.to_thread(_run)


async def resume_robots_v2_sessions() -> None:
    """Background task: restore trading sessions marked as running."""
    if not settings.ROBOTS_V2_ENABLED or not settings.ROBOTS_V2_AUTO_RESUME:
        return

    delay = float(getattr(settings, "SCHEDULER_STARTUP_DELAY_SECONDS", 15.0) or 15.0)
    await asyncio.sleep(min(max(delay, 2.0), 60.0))

    from app.modules.robots_v2.engine.session_manager import session_manager
    from app.modules.robots_v2.service import RobotsV2Service

    schema = getattr(settings, "DB_SCHEMA", None) or "public"
    db = SessionLocal()
    try:
        candidates = robots_to_resume(db, schema=schema)
    finally:
        db.close()

    if not candidates:
        logger.info("robots_v2 auto-resume: nothing to restore")
        return

    svc = RobotsV2Service()
    resumed = 0
    for item in candidates:
        robot_id = item["robot_id"]
        if session_manager.is_running(robot_id):
            continue
        try:
            closed = await close_orphan_audit_sessions(robot_id)
            if closed:
                logger.info(
                    "robots_v2 auto-resume robot=%s closed %s orphan audit session(s)",
                    robot_id,
                    closed,
                )
            db = SessionLocal()
            try:
                robot = svc.get_robot(db, item["user_id"], robot_id)
                await svc.launch_trading_session(
                    db,
                    robot,
                    user_id=item["user_id"],
                    stop_mode=str(item["metadata"].get("sessionStopMode") or "soft"),
                    mark_desired_running=True,
                )
                resumed += 1
                logger.info("robots_v2 auto-resume robot=%s OK", robot_id)
            finally:
                db.close()
        except Exception:
            logger.exception("robots_v2 auto-resume failed robot=%s", robot_id)

    logger.info(
        "robots_v2 auto-resume finished resumed=%s candidates=%s",
        resumed,
        len(candidates),
    )
