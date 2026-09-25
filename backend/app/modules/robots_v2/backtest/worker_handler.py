"""Heavy-lane handler for v2 backtest_run jobs (ARCH-05 phase A)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_db_context
from app.modules.robots_v2.backtest.persist import fetch_db_run_by_id, update_db_run
from app.modules.robots_v2.backtest.schemas import RobotV2BacktestRequest
from app.modules.robots_v2.backtest.store import BacktestRunRecord, backtest_run_store
from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4

logger = logging.getLogger(__name__)

JOB_TYPE_BACKTEST_RUN = "backtest_run"


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


async def handle_backtest_run(payload: dict[str, Any]) -> None:
    """Execute a queued v2 backtest. Payload: run_id, user_id, optional token_id."""
    run_id = int(payload["run_id"])
    user_id = int(payload["user_id"])
    token_id = payload.get("token_id")
    if token_id is not None:
        token_id = int(token_id)

    with get_db_context() as db:
        row = fetch_db_run_by_id(db, run_id)
    if row is None:
        raise RuntimeError(f"backtest_run job: run_id={run_id} not found")

    if int(row.get("user_id") or 0) != user_id:
        raise RuntimeError(f"backtest_run job: user mismatch run_id={run_id}")

    status = str(row.get("status") or "").upper()
    if status in ("SUCCESS", "FAILED", "CANCELLED"):
        logger.info("backtest_run skip terminal run_id=%s status=%s", run_id, status)
        return
    if row.get("cancel_requested"):
        with get_db_context() as db:
            update_db_run(
                db,
                run_id,
                status="CANCELLED",
                run_phase="cancelled",
                finished_at=datetime.now(timezone.utc),
                cancel_requested=True,
            )
        return

    snap = dict(row.get("config_snapshot") or {})
    snap.pop("engine_version", None)
    snap.pop("v2RobotId", None)
    try:
        config = TradingRobotConfigV4.model_validate(snap)
    except Exception as exc:
        raise RuntimeError(f"backtest_run invalid config run_id={run_id}: {exc}") from exc

    request = RobotV2BacktestRequest(
        config=snap,
        from_date=_parse_dt(row["requested_from"]),
        to_date=_parse_dt(row["requested_to"]),
        initial_capital=float(row.get("initial_capital") or config.risk.capital),
        robot_id=row.get("robot_id"),
        token_id=token_id,
        async_execution=True,
    )

    rec = BacktestRunRecord(
        run_id=run_id,
        user_id=user_id,
        robot_id=row.get("robot_id"),
        status="QUEUED",
        requested_from=request.from_date,
        requested_to=request.to_date,
        started_at=_parse_dt(row["started_at"]) if row.get("started_at") else request.from_date,
        initial_capital=float(request.initial_capital or 0),
        config_snapshot=snap,
        cancel_requested=bool(row.get("cancel_requested")),
    )
    await backtest_run_store.upsert(rec)

    from app.modules.robots_v2.backtest.service import backtest_service

    logger.info("backtest_run start run_id=%s user_id=%s", run_id, user_id)
    await backtest_service.execute_run(user_id, run_id, config, request)
    logger.info("backtest_run done run_id=%s", run_id)
