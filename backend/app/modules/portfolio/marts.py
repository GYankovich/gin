"""Writers for portfolio_snapshot_daily + portfolio_account_stats marts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.dashboard.queries import build_own_funds_query
from app.modules.dashboard.service import gain_vs_deposits_percent, percent_vs_base, resolve_day_change

MOSCOW = ZoneInfo("Europe/Moscow")


def _moscow_day(value: datetime) -> Any:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MOSCOW).date()


def upsert_portfolio_snapshot_daily(
    db: Session,
    *,
    snapshot_id: int,
    account_id: int,
    snapshot_date: datetime,
    total_amount_portfolio: Optional[float],
    daily_yield: Optional[float],
    expected_yield: Optional[float],
    currency: Optional[str],
) -> None:
    """UPSERT Moscow-day close row; day_delta vs previous day close."""
    day = _moscow_day(snapshot_date)
    prev = db.execute(
        text(
            """
            SELECT total_amount_portfolio
            FROM portfolio_snapshot_daily
            WHERE account_id = :account_id
              AND snapshot_day = :prev_day
            """
        ),
        {"account_id": account_id, "prev_day": day - timedelta(days=1)},
    ).first()
    day_delta = None
    if prev is not None and prev[0] is not None and total_amount_portfolio is not None:
        try:
            day_delta = float(total_amount_portfolio) - float(prev[0])
        except (TypeError, ValueError):
            day_delta = None

    db.execute(
        text(
            """
            INSERT INTO portfolio_snapshot_daily (
                id, account_id, snapshot_day, snapshot_date,
                total_amount_portfolio, daily_yield, expected_yield,
                currency, day_delta
            ) VALUES (
                :id, :account_id, :snapshot_day, :snapshot_date,
                :total, :daily_yield, :expected_yield,
                :currency, :day_delta
            )
            ON CONFLICT (account_id, snapshot_day) DO UPDATE SET
                id = EXCLUDED.id,
                snapshot_date = EXCLUDED.snapshot_date,
                total_amount_portfolio = EXCLUDED.total_amount_portfolio,
                daily_yield = EXCLUDED.daily_yield,
                expected_yield = EXCLUDED.expected_yield,
                currency = EXCLUDED.currency,
                day_delta = EXCLUDED.day_delta
            """
        ),
        {
            "id": snapshot_id,
            "account_id": account_id,
            "snapshot_day": day,
            "snapshot_date": snapshot_date,
            "total": total_amount_portfolio,
            "daily_yield": daily_yield,
            "expected_yield": expected_yield,
            "currency": currency,
            "day_delta": day_delta,
        },
    )


def refresh_account_stats_snapshot(
    db: Session,
    *,
    account_id: int,
    snapshot_id: int,
    snapshot_date: datetime,
    total_amount: Optional[float],
    currency: Optional[str],
    positions_count: Optional[int] = None,
) -> None:
    """Update equity / day Δ / gain after a new snapshot (keeps own_funds / W·L if set)."""
    cur = (currency or "RUB").upper()
    own_row = db.execute(
        text("SELECT own_funds, wins, losses, win_rate_percent, first_input_at, avg_monthly_roi_percent, ops_sync_version FROM portfolio_account_stats WHERE account_id = :id"),
        {"id": account_id},
    ).first()
    own_funds = float(own_row[0]) if own_row and own_row[0] is not None else None
    if own_funds is None and cur:
        q, params = build_own_funds_query(account_id, cur)
        of = db.execute(text(q), params).first()
        own_funds = float(of[0]) if of and of[0] is not None else None

    yesterday = db.execute(
        text(
            """
            SELECT total_amount_portfolio
            FROM portfolio_snapshot_daily
            WHERE account_id = :account_id
              AND snapshot_day = :yday
            """
        ),
        {"account_id": account_id, "yday": _moscow_day(snapshot_date) - timedelta(days=1)},
    ).first()
    y_total = float(yesterday[0]) if yesterday and yesterday[0] is not None else None
    day_delta, y_base = resolve_day_change(snapshot_date, y_total, float(total_amount or 0.0))
    day_pct = percent_vs_base(day_delta, y_base)
    gain_abs = None if own_funds is None or total_amount is None else float(total_amount) - own_funds
    gain_pct = gain_vs_deposits_percent(gain_abs, own_funds)

    db.execute(
        text(
            """
            INSERT INTO portfolio_account_stats (
                account_id, total_amount, currency, snapshot_id, snapshot_at,
                day_over_day_delta, day_over_day_percent,
                own_funds, gain_abs, gain_percent,
                wins, losses, win_rate_percent, first_input_at, avg_monthly_roi_percent,
                positions_count, computed_at, ops_sync_version
            ) VALUES (
                :account_id, :total, :currency, :snapshot_id, :snapshot_at,
                :day_delta, :day_pct,
                :own_funds, :gain_abs, :gain_pct,
                :wins, :losses, :win_rate, :first_input, :avg_monthly,
                :positions_count, :computed_at, :ops_ver
            )
            ON CONFLICT (account_id) DO UPDATE SET
                total_amount = EXCLUDED.total_amount,
                currency = EXCLUDED.currency,
                snapshot_id = EXCLUDED.snapshot_id,
                snapshot_at = EXCLUDED.snapshot_at,
                day_over_day_delta = EXCLUDED.day_over_day_delta,
                day_over_day_percent = EXCLUDED.day_over_day_percent,
                own_funds = COALESCE(EXCLUDED.own_funds, portfolio_account_stats.own_funds),
                gain_abs = EXCLUDED.gain_abs,
                gain_percent = EXCLUDED.gain_percent,
                positions_count = COALESCE(EXCLUDED.positions_count, portfolio_account_stats.positions_count),
                computed_at = EXCLUDED.computed_at
            """
        ),
        {
            "account_id": account_id,
            "total": total_amount,
            "currency": cur,
            "snapshot_id": snapshot_id,
            "snapshot_at": snapshot_date,
            "day_delta": day_delta,
            "day_pct": day_pct,
            "own_funds": own_funds,
            "gain_abs": gain_abs,
            "gain_pct": gain_pct,
            "wins": int(own_row[1]) if own_row and own_row[1] is not None else None,
            "losses": int(own_row[2]) if own_row and own_row[2] is not None else None,
            "win_rate": float(own_row[3]) if own_row and own_row[3] is not None else None,
            "first_input": own_row[4] if own_row else None,
            "avg_monthly": float(own_row[5]) if own_row and own_row[5] is not None else None,
            "positions_count": positions_count,
            "computed_at": datetime.now(timezone.utc),
            "ops_ver": int(own_row[6]) if own_row and own_row[6] is not None else 0,
        },
    )


def refresh_account_stats_after_ops(db: Session, account_id: int) -> None:
    """Recompute own_funds + FIFO W·L / ROI after operations sync."""
    from app.modules.analytics.service import AnalyticsService

    latest = db.execute(
        text(
            """
            SELECT id, total_amount_portfolio, snapshot_date, currency
            FROM portfolio_snapshots
            WHERE account_id = :account_id
            ORDER BY snapshot_date DESC
            LIMIT 1
            """
        ),
        {"account_id": account_id},
    ).first()
    if not latest:
        return

    snapshot_id = int(latest[0])
    total = float(latest[1] or 0.0)
    snap_at = latest[2]
    currency = str(latest[3] or "RUB").upper()

    q, params = build_own_funds_query(account_id, currency)
    of = db.execute(text(q), params).first()
    own_funds = float(of[0]) if of and of[0] is not None else None

    analytics = AnalyticsService()
    far_past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    far_future = datetime.now(timezone.utc) + timedelta(days=1)
    fifo = analytics._build_fifo_trade_metrics(db, account_id, far_past, far_future)
    wins = fifo.get("winning_trades_count")
    losses = fifo.get("losing_trades_count")
    win_rate = fifo.get("win_rate_percent")

    first_input = db.execute(
        text(
            """
            SELECT MIN(operation_date)
            FROM portfolio_operations
            WHERE account_id = :account_id
              AND operation_type IN (
                    'OPERATION_TYPE_INPUT',
                    'OPERATION_TYPE_INPUT_ACQUIRING',
                    'OPERATION_TYPE_INP_MULTI'
              )
              AND status = 'OPERATION_STATE_EXECUTED'
            """
        ),
        {"account_id": account_id},
    ).first()
    first_at = first_input[0] if first_input else None

    gain_abs = None if own_funds is None else total - own_funds
    gain_pct = gain_vs_deposits_percent(gain_abs, own_funds)
    avg_monthly = None
    if gain_pct is not None and first_at is not None and snap_at is not None:
        months = max((snap_at - first_at).total_seconds() / (86400.0 * 30.4375), 0.0)
        if months > 1e-9:
            avg_monthly = gain_pct / months

    upsert_portfolio_snapshot_daily(
        db,
        snapshot_id=snapshot_id,
        account_id=account_id,
        snapshot_date=snap_at,
        total_amount_portfolio=total,
        daily_yield=None,
        expected_yield=None,
        currency=currency,
    )
    # stamp own_funds_eod on today's daily row
    db.execute(
        text(
            """
            UPDATE portfolio_snapshot_daily
            SET own_funds_eod = :own_funds
            WHERE account_id = :account_id
              AND snapshot_day = :day
            """
        ),
        {"own_funds": own_funds, "account_id": account_id, "day": _moscow_day(snap_at)},
    )

    yesterday = db.execute(
        text(
            """
            SELECT total_amount_portfolio
            FROM portfolio_snapshot_daily
            WHERE account_id = :account_id AND snapshot_day = :yday
            """
        ),
        {"account_id": account_id, "yday": _moscow_day(snap_at) - timedelta(days=1)},
    ).first()
    y_total = float(yesterday[0]) if yesterday and yesterday[0] is not None else None
    day_delta, y_base = resolve_day_change(snap_at, y_total, total)
    day_pct = percent_vs_base(day_delta, y_base)

    prev_ver = db.execute(
        text("SELECT ops_sync_version FROM portfolio_account_stats WHERE account_id = :id"),
        {"id": account_id},
    ).first()
    ops_ver = (int(prev_ver[0]) if prev_ver and prev_ver[0] is not None else 0) + 1

    db.execute(
        text(
            """
            INSERT INTO portfolio_account_stats (
                account_id, total_amount, currency, snapshot_id, snapshot_at,
                day_over_day_delta, day_over_day_percent,
                own_funds, gain_abs, gain_percent,
                wins, losses, win_rate_percent, first_input_at, avg_monthly_roi_percent,
                computed_at, ops_sync_version
            ) VALUES (
                :account_id, :total, :currency, :snapshot_id, :snapshot_at,
                :day_delta, :day_pct,
                :own_funds, :gain_abs, :gain_pct,
                :wins, :losses, :win_rate, :first_input, :avg_monthly,
                :computed_at, :ops_ver
            )
            ON CONFLICT (account_id) DO UPDATE SET
                total_amount = EXCLUDED.total_amount,
                currency = EXCLUDED.currency,
                snapshot_id = EXCLUDED.snapshot_id,
                snapshot_at = EXCLUDED.snapshot_at,
                day_over_day_delta = EXCLUDED.day_over_day_delta,
                day_over_day_percent = EXCLUDED.day_over_day_percent,
                own_funds = EXCLUDED.own_funds,
                gain_abs = EXCLUDED.gain_abs,
                gain_percent = EXCLUDED.gain_percent,
                wins = EXCLUDED.wins,
                losses = EXCLUDED.losses,
                win_rate_percent = EXCLUDED.win_rate_percent,
                first_input_at = EXCLUDED.first_input_at,
                avg_monthly_roi_percent = EXCLUDED.avg_monthly_roi_percent,
                computed_at = EXCLUDED.computed_at,
                ops_sync_version = EXCLUDED.ops_sync_version
            """
        ),
        {
            "account_id": account_id,
            "total": total,
            "currency": currency,
            "snapshot_id": snapshot_id,
            "snapshot_at": snap_at,
            "day_delta": day_delta,
            "day_pct": day_pct,
            "own_funds": own_funds,
            "gain_abs": gain_abs,
            "gain_pct": gain_pct,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "first_input": first_at,
            "avg_monthly": avg_monthly,
            "computed_at": datetime.now(timezone.utc),
            "ops_ver": ops_ver,
        },
    )
