"""Run one portfolio sync cycle for a robots_v2 type=1 robot."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.robots.trading.brokers.routing import enforce_broker_for_token
from app.modules.robots.portfolio_updater.robot import PortfolioUpdaterRobot
from app.modules.robots_v2.portfolio.queries import (
    build_find_portfolio_v2_by_token_query,
    build_update_portfolio_last_started_query,
)
from app.modules.robots_v2.portfolio.schedule import should_run_portfolio

logger = logging.getLogger(__name__)


def resolve_portfolio_v2_robot_id(db: Session, payload: dict[str, Any]) -> int | None:
    """Resolve v2 portfolio robot id from job payload (scheduler or legacy trading enqueue)."""
    schema = settings.DB_SCHEMA or "public"
    robot_id = payload.get("robot_id")
    if robot_id is not None:
        row = db.execute(
            text(
                f"""
                SELECT id, type
                FROM {schema}.robots_v2
                WHERE id = :id
                  AND COALESCE(metadata->>'deletedAt', '') = ''
                """
            ),
            {"id": int(robot_id)},
        ).fetchone()
        if row is not None and int(row.type) == 1:
            return int(row.id)

    token_id = payload.get("token_id")
    user_id = payload.get("user_id")
    if token_id is None or user_id is None:
        return None
    found = db.execute(
        text(build_find_portfolio_v2_by_token_query(schema=schema)),
        {"token_id": int(token_id), "user_id": int(user_id)},
    ).fetchone()
    return int(found.id) if found is not None else None


async def run_portfolio_sync_v2(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    schema = settings.DB_SCHEMA or "public"
    robot_id = resolve_portfolio_v2_robot_id(db, payload)
    if robot_id is None:
        logger.warning("portfolio_sync: no v2 portfolio robot for payload=%s", payload)
        return {"status": "skipped", "reason": "portfolio robot not found"}

    row = db.execute(
        text(
            f"""
            SELECT r.id, r.user_id, r.token_id, r.config, r.last_started,
                   at.token AS token_value, at.extra_data, at.token_type,
                   da.string_value AS broker_type
            FROM {schema}.robots_v2 r
            INNER JOIN {schema}.api_tokens at ON r.token_id = at.id
            LEFT JOIN {schema}.dictionary da
                   ON at.token_type = da.num_value
                  AND da.table_name = 'TOKEN'
                  AND da.column_name = 'TYPE'
            WHERE r.id = :robot_id
              AND r.type = 1
              AND r.status = 1
              AND COALESCE(r.metadata->>'deletedAt', '') = ''
              AND at.status = 1
            """
        ),
        {"robot_id": robot_id},
    ).fetchone()
    if row is None:
        return {"status": "skipped", "reason": "robot disabled or token inactive"}

    config = row.config if isinstance(row.config, dict) else {}
    last_started = row.last_started
    ok, skip_reason = should_run_portfolio(config, last_started)
    if not ok:
        logger.info("portfolio_sync v2 robot_id=%s skipped: %s", robot_id, skip_reason)
        return {"status": "skipped", "reason": skip_reason}

    token_type = int(row.token_type) if row.token_type is not None else None
    broker_type = enforce_broker_for_token(
        str(row.broker_type or payload.get("broker_type") or ""),
        token_type=token_type,
        token_type_name=str(row.broker_type or ""),
        mutate=False,
        require_token=True,
    )
    token_extra = row.extra_data if isinstance(row.extra_data, dict) else payload.get("token_extra_data") or {}

    updater = PortfolioUpdaterRobot("scheduler-v2")
    updater.db = db
    try:
        result = await updater.execute(
            robot_id=int(row.id),
            user_id=int(row.user_id),
            token_id=int(row.token_id),
            token=str(row.token_value or payload.get("token") or ""),
            broker_type=broker_type,
            token_extra_data=token_extra,
            caller="scheduler",
        )
        now = datetime.now(timezone.utc)
        db.execute(
            text(build_update_portfolio_last_started_query(schema=schema)),
            {"robot_id": robot_id, "now": now},
        )
        logger.info(
            "portfolio_sync v2 robot_id=%s status=%s snapshots=%s",
            robot_id,
            result.get("status"),
            result.get("snapshots_saved"),
        )
        return result
    except Exception:
        raise
