from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session


def fetch_successful_backtests(
    db: Session,
    schema: str,
    robot_id: int,
    limit: int = 15,
) -> List[Tuple[Any, ...]]:
    sql = f"""
        SELECT
            br.id,
            br.status,
            br.requested_from,
            br.requested_to,
            br.config_snapshot,
            br.started_at,
            bm.total_return_percent,
            bm.max_drawdown_percent,
            bm.win_rate_percent,
            bm.trades_total,
            bm.sharpe_ratio,
            COALESCE(bm.payload, '{{}}'::jsonb) AS payload
        FROM backtest_runs br
        LEFT JOIN backtest_metrics bm ON bm.run_id = br.id
        WHERE br.robot_id = :robot_id
          AND br.status = 'SUCCESS'
        ORDER BY br.started_at DESC
        LIMIT :limit
    """
    return db.execute(text(sql), {"robot_id": robot_id, "limit": limit}).fetchall()


def fetch_failed_backtests(
    db: Session,
    schema: str,
    *,
    user_id: int,
    robot_id: Optional[int] = None,
    limit: int = 20,
) -> List[Tuple[Any, ...]]:
    if robot_id is not None:
        scope_sql = """
            br.user_id = :user_id
            AND (br.robot_id = :robot_id OR br.robot_id IS NULL)
        """
        params: Dict[str, Any] = {"user_id": user_id, "robot_id": robot_id, "limit": limit}
    else:
        scope_sql = """
            br.user_id = :user_id
            AND br.robot_id IS NULL
        """
        params = {"user_id": user_id, "limit": limit}

    sql = f"""
        SELECT
            br.id,
            br.status,
            br.requested_from,
            br.requested_to,
            br.config_snapshot,
            br.started_at,
            br.error_message
        FROM backtest_runs br
        WHERE {scope_sql}
          AND br.status = 'FAILED'
          AND COALESCE(br.error_message, '') <> ''
        ORDER BY br.started_at DESC
        LIMIT :limit
    """
    return db.execute(text(sql), params).fetchall()


def fetch_latest_backtest_any_status(
    db: Session,
    schema: str,
    robot_id: int,
) -> Optional[Tuple[Any, ...]]:
    sql = f"""
        SELECT
            br.id,
            br.status,
            br.requested_from,
            br.requested_to,
            br.config_snapshot,
            br.started_at,
            bm.total_return_percent,
            bm.max_drawdown_percent,
            bm.win_rate_percent,
            bm.trades_total,
            bm.sharpe_ratio,
            COALESCE(bm.payload, '{{}}'::jsonb) AS payload
        FROM backtest_runs br
        LEFT JOIN backtest_metrics bm ON bm.run_id = br.id
        WHERE br.robot_id = :robot_id
        ORDER BY br.started_at DESC
        LIMIT 1
    """
    return db.execute(text(sql), {"robot_id": robot_id}).first()


def fetch_risk_events_count(
    db: Session,
    schema: str,
    robot_id: int,
    days: int = 7,
) -> int:
    sql = f"""
        SELECT COUNT(*)::int
        FROM robot_risk_events
        WHERE robot_id = :robot_id
          AND ts >= NOW() - make_interval(days => :days)
    """
    return int(
        db.execute(text(sql), {"robot_id": robot_id, "days": days}).scalar() or 0
    )


def fetch_signal_execution_stats(
    db: Session,
    schema: str,
    robot_id: int,
    limit: int = 200,
) -> Dict[str, int]:
    sql = f"""
        SELECT
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE was_executed = 1)::int AS executed
        FROM (
            SELECT was_executed
            FROM robot_signals
            WHERE robot_id = :robot_id
            ORDER BY created_at DESC
            LIMIT :limit
        ) s
    """
    row = db.execute(text(sql), {"robot_id": robot_id, "limit": limit}).first()
    if not row:
        return {"total": 0, "executed": 0}
    return {"total": int(row[0] or 0), "executed": int(row[1] or 0)}
