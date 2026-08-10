from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session


def has_active_batch(db: Session, schema: str, robot_id: int) -> bool:
    row = db.execute(
        text(f"""
            SELECT 1
            FROM optimization_batches
            WHERE robot_id = :robot_id
              AND status IN ('queued', 'running')
            LIMIT 1
        """),
        {"robot_id": robot_id},
    ).first()
    return row is not None


def insert_batch(
    db: Session,
    schema: str,
    *,
    robot_id: int,
    user_id: int,
    goal: str,
    mode: str,
    total_candidates: int,
    requested_from: datetime,
    requested_to: datetime,
    initial_capital: float,
) -> int:
    batch_id = int(
        db.execute(
            text(f"""
                INSERT INTO optimization_batches
                    (robot_id, user_id, goal, mode, status, total_candidates,
                     requested_from, requested_to, initial_capital, started_at)
                VALUES
                    (:robot_id, :user_id, :goal, :mode, 'running', :total,
                     :requested_from, :requested_to, :initial_capital, CURRENT_TIMESTAMP)
                RETURNING id
            """),
            {
                "robot_id": robot_id,
                "user_id": user_id,
                "goal": goal,
                "mode": mode,
                "total": total_candidates,
                "requested_from": requested_from,
                "requested_to": requested_to,
                "initial_capital": initial_capital,
            },
        ).scalar()
    )
    return batch_id


def insert_batch_item(
    db: Session,
    schema: str,
    *,
    batch_id: int,
    candidate_index: int,
    run_id: int,
    param_summary: Dict[str, Any],
) -> None:
    db.execute(
        text(f"""
            INSERT INTO optimization_batch_items
                (batch_id, candidate_index, run_id, param_summary, status)
            VALUES
                (:batch_id, :candidate_index, :run_id, CAST(:param_summary AS jsonb), 'queued')
        """),
        {
            "batch_id": batch_id,
            "candidate_index": candidate_index,
            "run_id": run_id,
            "param_summary": json.dumps(param_summary or {}, ensure_ascii=False),
        },
    )


def fetch_batch_header(
    db: Session,
    schema: str,
    batch_id: int,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    row = db.execute(
        text(f"""
            SELECT id, robot_id, user_id, goal, mode, status, total_candidates,
                   requested_from, requested_to, initial_capital,
                   overfitting_warnings, error_message,
                   created_at, started_at, finished_at
            FROM optimization_batches
            WHERE id = :batch_id AND user_id = :user_id
        """),
        {"batch_id": batch_id, "user_id": user_id},
    ).mappings().first()
    return dict(row) if row else None


def fetch_active_batch_for_robot(
    db: Session,
    schema: str,
    robot_id: int,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    row = db.execute(
        text(f"""
            SELECT id, robot_id, user_id, goal, mode, status, total_candidates,
                   requested_from, requested_to, initial_capital,
                   overfitting_warnings, error_message,
                   created_at, started_at, finished_at
            FROM optimization_batches
            WHERE robot_id = :robot_id
              AND user_id = :user_id
              AND status IN ('queued', 'running')
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"robot_id": robot_id, "user_id": user_id},
    ).mappings().first()
    return dict(row) if row else None


def fetch_batch_items(db: Session, schema: str, batch_id: int) -> List[Dict[str, Any]]:
    rows = db.execute(
        text(f"""
            SELECT
                i.id,
                i.candidate_index,
                i.run_id,
                i.param_summary,
                i.status AS item_status,
                i.score,
                br.status AS run_status,
                br.error_message,
                br.config_snapshot,
                bm.total_return_percent,
                bm.max_drawdown_percent,
                bm.win_rate_percent,
                bm.trades_total,
                bm.sharpe_ratio
            FROM optimization_batch_items i
            LEFT JOIN backtest_runs br ON br.id = i.run_id
            LEFT JOIN backtest_metrics bm ON bm.run_id = i.run_id
            WHERE i.batch_id = :batch_id
            ORDER BY i.candidate_index ASC
        """),
        {"batch_id": batch_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def update_batch_status(
    db: Session,
    schema: str,
    batch_id: int,
    *,
    status: str,
    overfitting_warnings: Optional[List[str]] = None,
    error_message: Optional[str] = None,
) -> None:
    db.execute(
        text(f"""
            UPDATE optimization_batches
            SET status = :status,
                finished_at = CASE WHEN :status IN ('completed', 'failed', 'cancelled')
                    THEN COALESCE(finished_at, CURRENT_TIMESTAMP) ELSE finished_at END,
                overfitting_warnings = COALESCE(CAST(:warnings AS jsonb), overfitting_warnings),
                error_message = COALESCE(:error_message, error_message)
            WHERE id = :batch_id
        """),
        {
            "batch_id": batch_id,
            "status": status,
            "warnings": json.dumps(overfitting_warnings or [], ensure_ascii=False) if overfitting_warnings else None,
            "error_message": error_message,
        },
    )


def update_batch_item_from_run(
    db: Session,
    schema: str,
    *,
    batch_id: int,
    run_id: int,
    status: str,
    score: Optional[float],
) -> None:
    db.execute(
        text(f"""
            UPDATE optimization_batch_items
            SET status = :status,
                score = :score
            WHERE batch_id = :batch_id AND run_id = :run_id
        """),
        {"batch_id": batch_id, "run_id": run_id, "status": status.lower(), "score": score},
    )


def fetch_batch_run_ids(db: Session, schema: str, batch_id: int) -> List[int]:
    rows = db.execute(
        text(f"""
            SELECT run_id FROM optimization_batch_items
            WHERE batch_id = :batch_id AND run_id IS NOT NULL
            ORDER BY candidate_index
        """),
        {"batch_id": batch_id},
    ).fetchall()
    return [int(r[0]) for r in rows if r[0] is not None]
