"""Optional DB persistence for v2 backtest runs (public.backtest_runs)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def create_db_run(
    db: Session,
    *,
    user_id: int,
    robot_id: int | None,
    requested_from: datetime,
    requested_to: datetime,
    initial_capital: float,
    config_snapshot: dict[str, Any],
) -> int | None:
    params = {
        "robot_id": robot_id,
        "user_id": user_id,
        "requested_from": requested_from,
        "requested_to": requested_to,
        "started_at": datetime.now(timezone.utc),
        "board": "TQBR",
        "initial_capital": initial_capital,
        "config_snapshot": json.dumps(
            {**config_snapshot, "engine_version": "v2"},
            ensure_ascii=False,
        ),
        "execution_model": json.dumps({"engine_version": "v2", "model": "BAR_CLOSE"}, ensure_ascii=False),
    }
    sql_variants = [
        """
        INSERT INTO backtest_runs
        (robot_id, user_id, requested_from, requested_to, started_at, status, board,
         initial_capital, config_snapshot, execution_model, cancel_requested, partial_result,
         run_phase)
        VALUES
        (:robot_id, :user_id, :requested_from, :requested_to, :started_at, 'QUEUED', :board,
         :initial_capital, CAST(:config_snapshot AS jsonb), CAST(:execution_model AS jsonb),
         false, false, 'queued')
        RETURNING id
        """,
        """
        INSERT INTO backtest_runs
        (robot_id, user_id, requested_from, requested_to, started_at, status, board,
         initial_capital, config_snapshot, execution_model, cancel_requested, partial_result)
        VALUES
        (:robot_id, :user_id, :requested_from, :requested_to, :started_at, 'QUEUED', :board,
         :initial_capital, CAST(:config_snapshot AS jsonb), CAST(:execution_model AS jsonb),
         false, false)
        RETURNING id
        """,
    ]
    for sql in sql_variants:
        try:
            run_id = db.execute(text(sql), params).scalar()
            db.commit()
            return int(run_id) if run_id is not None else None
        except Exception as exc:
            logger.warning("v2 backtest DB create attempt failed: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass
    return None


def update_db_run(db: Session, run_id: int, **fields: Any) -> None:
    if not fields:
        return
    allowed = {
        "status", "run_phase", "progress_percent", "phase_units_done", "phase_units_total",
        "finished_at", "error_message", "cancel_requested",
    }
    sets = []
    params: dict[str, Any] = {"rid": run_id}
    for key, value in fields.items():
        if key not in allowed:
            continue
        sets.append(f"{key} = :{key}")
        params[key] = value
    if not sets:
        return
    try:
        db.execute(text(f"UPDATE backtest_runs SET {', '.join(sets)} WHERE id = :rid"), params)
        db.commit()
    except Exception as exc:
        logger.warning("v2 backtest DB update failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass


def persist_result_payload(db: Session, run_id: int, payload: dict[str, Any]) -> None:
    """Best-effort: store summary + optional full payload."""
    summary = {
        "total_return_percent": payload.get("total_return_percent"),
        "max_drawdown_percent": payload.get("max_drawdown_percent"),
        "trades_total": len(payload.get("trades") or []),
        "final_equity": payload.get("final_equity"),
        "engine_version": "v2",
        "stages": payload.get("stages") or [],
        "history_stats": payload.get("history_stats") or {},
        "equity_curve": payload.get("equity_curve") or [],
        "trades": payload.get("trades") or [],
    }
    try:
        db.execute(
            text("""
                UPDATE backtest_runs
                SET metrics_summary = CAST(:summary AS jsonb)
                WHERE id = :rid
            """),
            {
                "rid": run_id,
                "summary": json.dumps(summary, ensure_ascii=False),
            },
        )
        db.commit()
    except Exception as exc:
        logger.warning("v2 backtest metrics persist failed run_id=%s: %s", run_id, exc)
        try:
            db.rollback()
        except Exception:
            pass

