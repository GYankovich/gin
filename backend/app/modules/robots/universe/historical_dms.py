"""Apply DMS pipeline filters on historical (as-of) rows for V2 universe."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.dms.service import dms_service


def load_snapshot_rows_for_day(
    db: Session,
    *,
    board: str,
    day: date,
) -> list[dict[str, Any]]:
    """Load SUCCESS snapshot history rows for board/day (nearest SUCCESS that day)."""
    board_u = (board or "TQBR").strip().upper() or "TQBR"
    day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    snap_id = db.execute(
        text(
            """
            SELECT id
            FROM market_snapshot_history
            WHERE board = :board
              AND status = 'SUCCESS'
              AND snapshot_time >= :day_start
              AND snapshot_time < :day_end
            ORDER BY snapshot_time DESC
            LIMIT 1
            """
        ),
        {"board": board_u, "day_start": day_start, "day_end": day_end},
    ).scalar()
    if snap_id is None:
        return []
    rows = db.execute(
        text(
            """
            SELECT ticker, last_price, open_price, high_price, low_price, prev_price, value_today,
                   volume_lots, bid, ask, spread, security_status, trading_status, num_trades,
                   issue_size, min_step, prev_legal_close_price, isin, lot_size, close_price,
                   securities_payload
            FROM market_snapshot_data_history
            WHERE snapshot_id = :snapshot_id
            """
        ),
        {"snapshot_id": int(snap_id)},
    ).mappings().all()
    return [dict(r) for r in rows]


def apply_dms_filters_historical(
    rows: list[dict[str, Any]],
    *,
    dms_filters: list[dict[str, Any]],
    mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Run the same ``_evaluate_pipeline_row`` as live DMS.

    ``allow_missing_spread=True`` — historical PIT rows often lack bid/ask.
    Returns (accepted_rows, rejected_meta[{ticker, reason}]).
    """
    if not dms_filters:
        return list(rows), []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    eval_mode = "ANY" if str(mode).upper() == "ANY" else "ALL"
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        eval_row = dict(row)
        eval_row["ticker"] = ticker
        # Defaults so status filters don't nuke PIT-only candles rows.
        if not eval_row.get("security_status"):
            eval_row["security_status"] = "A"
        if not eval_row.get("trading_status"):
            eval_row["trading_status"] = "T"
        if eval_row.get("last_price") and not eval_row.get("open_price"):
            eval_row["open_price"] = eval_row["last_price"]
        if eval_row.get("last_price") and not eval_row.get("prev_price"):
            eval_row["prev_price"] = eval_row["last_price"]
        try:
            res = dms_service._evaluate_pipeline_row(
                eval_row,
                dms_filters,
                eval_mode,
                optimize_order=True,
                allow_missing_spread=True,
            )
        except Exception as exc:
            rejected.append({"ticker": ticker, "reason": f"dms_error:{exc}"})
            continue
        if res.get("accepted"):
            accepted.append(row)
        else:
            rejected.append({
                "ticker": ticker,
                "reason": str(res.get("reason") or "rejected"),
            })
    return accepted, rejected
