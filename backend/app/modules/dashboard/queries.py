"""Query builders and read helpers for the dashboard module."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.modules.portfolio.models import PortfolioAccount


def build_own_funds_query(account_id: int) -> Tuple[str, Dict[str, Any]]:
    """Build the query that calculates deposited account funds."""
    return """
        SELECT
            COALESCE(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_INPUT' THEN payment ELSE 0 END), 0)
            -
            COALESCE(SUM(CASE WHEN operation_type = 'OPERATION_TYPE_OUTPUT' THEN ABS(payment) ELSE 0 END), 0)
        FROM portfolio_operations
        WHERE account_id = :account_id
        """, {"account_id": account_id}


def build_latest_snapshot_query(account_id: int) -> Tuple[str, Dict[str, Any]]:
    """Build the query for an account's most recent portfolio snapshot."""
    return """
        SELECT total_amount_portfolio, snapshot_date, daily_yield, currency
        FROM portfolio_snapshots
        WHERE account_id = :account_id
        ORDER BY snapshot_date DESC
        LIMIT 1
        """, {"account_id": account_id}


def build_previous_day_total_query(
    account_id: int,
    latest_snapshot_date: datetime,
) -> Tuple[str, Dict[str, Any]]:
    """Build the query for the snapshot preceding the latest snapshot's day."""
    return """
        SELECT total_amount_portfolio
        FROM portfolio_snapshots
        WHERE account_id = :account_id
          AND snapshot_date < date_trunc('day', CAST(:latest_ts AS timestamptz))
        ORDER BY snapshot_date DESC
        LIMIT 1
        """, {"account_id": account_id, "latest_ts": latest_snapshot_date}


def build_account_opened_query(account_id: int) -> Tuple[str, Dict[str, Any]]:
    """Build the query that resolves the account's first snapshot date."""
    return """
        SELECT MIN(snapshot_date)
        FROM portfolio_snapshots
        WHERE account_id = :account_id
        """, {"account_id": account_id}


def build_assets_query(
    user_id: int,
    included_account_ids: Optional[List[int]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Build the asset-allocation query from each open account's latest snapshot."""
    params: Dict[str, Any] = {"user_id": user_id}
    account_filter = ""
    if included_account_ids is not None:
        account_filter = "AND pa.id = ANY(:account_ids)"
        params["account_ids"] = included_account_ids

    query = f"""
        WITH latest_snapshots AS (
            SELECT DISTINCT ON (ps.account_id)
                ps.id AS snapshot_id,
                UPPER(COALESCE(ps.currency, 'RUB')) AS currency,
                COALESCE(ps.total_amount_shares, 0) AS shares,
                COALESCE(ps.total_amount_bonds, 0) AS bonds,
                COALESCE(ps.total_amount_etf, 0) AS etf,
                COALESCE(ps.total_amount_currencies, 0) AS currencies,
                COALESCE(ps.total_amount_futures, 0) AS futures,
                COALESCE(ps.total_amount_options, 0) AS options
            FROM portfolio_snapshots ps
            INNER JOIN portfolio_accounts pa
                ON pa.id = ps.account_id
            WHERE pa.user_id = :user_id
              AND pa.account_status = 'OPEN'
              {account_filter}
            ORDER BY ps.account_id, ps.snapshot_date DESC
        ),
        snap_by_type AS (
            SELECT currency, 'share' AS instrument_type, SUM(shares) AS value
            FROM latest_snapshots GROUP BY currency
            UNION ALL
            SELECT currency, 'bond', SUM(bonds)
            FROM latest_snapshots GROUP BY currency
            UNION ALL
            SELECT currency, 'etf', SUM(etf)
            FROM latest_snapshots GROUP BY currency
            UNION ALL
            SELECT currency, 'currency', SUM(currencies)
            FROM latest_snapshots GROUP BY currency
            UNION ALL
            SELECT currency, 'future', SUM(futures)
            FROM latest_snapshots GROUP BY currency
            UNION ALL
            SELECT currency, 'option', SUM(options)
            FROM latest_snapshots GROUP BY currency
        ),
        day_by_type AS (
            SELECT
                ls.currency,
                pp.instrument_type,
                SUM(pp.daily_yield) AS day_delta,
                BOOL_OR(pp.daily_yield IS NOT NULL) AS has_day_delta
            FROM latest_snapshots ls
            INNER JOIN portfolio_positions pp
                ON pp.snapshot_id = ls.snapshot_id
            GROUP BY ls.currency, pp.instrument_type
        ),
        joined AS (
            SELECT
                s.currency,
                COALESCE(d.name, s.instrument_type, 'Прочее') AS asset_type,
                s.value,
                CASE WHEN dy.has_day_delta THEN dy.day_delta ELSE NULL END AS day_delta
            FROM snap_by_type s
            LEFT JOIN day_by_type dy
                ON dy.currency = s.currency
               AND dy.instrument_type = s.instrument_type
            LEFT JOIN dictionary d
                ON d.table_name = 'PORTFOLIO_POSITIONS'
               AND d.column_name = 'INSTRUMENT_TYPE'
               AND d.string_value = s.instrument_type
               AND d.hide_from_ui = 0
            WHERE ABS(s.value) > 1e-9
        ),
        totals AS (
            SELECT currency, SUM(value) AS total_value
            FROM joined
            GROUP BY currency
        )
        SELECT
            j.asset_type AS type,
            j.value,
            CASE
                WHEN t.total_value IS NULL OR ABS(t.total_value) < 1e-9 THEN 0
                ELSE ROUND((j.value / t.total_value) * 100)::int
            END AS percent,
            j.currency,
            j.day_delta AS day_over_day_delta
        FROM joined j
        INNER JOIN totals t ON t.currency = j.currency
        ORDER BY j.currency, j.value DESC
    """
    return query, params


def list_open_accounts(db: Session, user_id: int) -> List[PortfolioAccount]:
    """Return a user's open portfolio accounts."""
    return (
        db.query(PortfolioAccount)
        .filter(
            PortfolioAccount.user_id == user_id,
            PortfolioAccount.account_status == "OPEN",
        )
        .all()
    )


def get_account_for_visibility(
    db: Session,
    user_id: int,
    account_id: int,
) -> Optional[PortfolioAccount]:
    """Return a user-owned account eligible for a visibility update."""
    return (
        db.query(PortfolioAccount)
        .filter(
            PortfolioAccount.id == account_id,
            PortfolioAccount.user_id == user_id,
        )
        .first()
    )
