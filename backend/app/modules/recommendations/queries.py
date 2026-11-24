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
    """Risk denies from robot_decisions (legacy robot_risk_events retired)."""
    sql = f"""
        SELECT COUNT(*)::int
        FROM {schema}.robot_decisions
        WHERE robot_id = :robot_id
          AND stage = 'risk'
          AND outcome = 'deny'
          AND created_at >= NOW() - make_interval(days => :days)
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
    """Signals that got a same-cycle/ticker order (legacy robot_signals retired)."""
    sql = f"""
        SELECT
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE executed = 1)::int AS executed
        FROM (
            SELECT
                CASE WHEN EXISTS (
                    SELECT 1
                    FROM {schema}.robot_orders o
                    WHERE o.robot_id = s.robot_id
                      AND o.cycle_id = s.cycle_id
                      AND o.ticker = s.ticker
                ) THEN 1 ELSE 0 END AS executed
            FROM {schema}.robot_signals s
            WHERE s.robot_id = :robot_id
            ORDER BY s.created_at DESC
            LIMIT :limit
        ) x
    """
    row = db.execute(text(sql), {"robot_id": robot_id, "limit": limit}).first()
    if not row:
        return {"total": 0, "executed": 0}
    return {"total": int(row[0] or 0), "executed": int(row[1] or 0)}
