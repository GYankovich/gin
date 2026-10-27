"""Query builders and read helpers for the dashboard module."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.portfolio.models import PortfolioAccount


def build_own_funds_query(account_id: int, currency: str) -> Tuple[str, Dict[str, Any]]:
    """Net external cash in the snapshot currency. No matching rows → NULL, not zero."""
    return """
        SELECT SUM(signed_payment)
        FROM (
            SELECT
                CASE
                    WHEN operation_type IN (
                        'OPERATION_TYPE_INPUT',
                        'OPERATION_TYPE_INPUT_ACQUIRING',
                        'OPERATION_TYPE_INP_MULTI'
                    )
                    AND status = 'OPERATION_STATE_EXECUTED'
                    AND UPPER(payment_currency) = :currency
                    AND ABS(payment) > 1e-9
                        THEN payment
                    WHEN operation_type IN (
                        'OPERATION_TYPE_OUTPUT',
                        'OPERATION_TYPE_OUTPUT_ACQUIRING',
                        'OPERATION_TYPE_OUT_MULTI'
                    )
                    AND status = 'OPERATION_STATE_EXECUTED'
                    AND UPPER(payment_currency) = :currency
                    AND ABS(payment) > 1e-9
                        THEN -ABS(payment)
                    WHEN operation_type LIKE 'BYBIT_FUND_IN%'
                    AND UPPER(payment_currency) = :currency
                        THEN CASE
                            WHEN ABS(payment) > 1e-9 THEN payment
                            WHEN ABS(quantity) > 1e-9 THEN ABS(quantity)
                            ELSE NULL
                        END
                    WHEN operation_type LIKE 'BYBIT_FUND_OUT%'
                    AND UPPER(payment_currency) = :currency
                        THEN CASE
                            WHEN ABS(payment) > 1e-9 THEN -ABS(payment)
                            WHEN ABS(quantity) > 1e-9 THEN -ABS(quantity)
                            ELSE NULL
                        END
                    WHEN operation_type LIKE 'BYBIT_TRANSFER_IN%'
                    AND UPPER(payment_currency) = :currency
                        THEN CASE
                            WHEN ABS(payment) > 1e-9 THEN payment
                            WHEN ABS(quantity) > 1e-9 THEN ABS(quantity)
                            ELSE NULL
                        END
                    WHEN operation_type LIKE 'BYBIT_TRANSFER_OUT%'
                    AND UPPER(payment_currency) = :currency
                        THEN CASE
                            WHEN ABS(payment) > 1e-9 THEN -ABS(payment)
                            WHEN ABS(quantity) > 1e-9 THEN -ABS(quantity)
                            ELSE NULL
                        END
                    ELSE NULL
                END AS signed_payment
            FROM portfolio_operations
            WHERE account_id = :account_id
        ) cashflows
        WHERE signed_payment IS NOT NULL
        """, {"account_id": account_id, "currency": currency.upper()}


def build_latest_snapshot_query(account_id: int) -> Tuple[str, Dict[str, Any]]:
    """Build the query for an account's most recent portfolio snapshot."""
    return """
        SELECT total_amount_portfolio, snapshot_date, currency
        FROM portfolio_snapshots
        WHERE account_id = :account_id
        ORDER BY snapshot_date DESC
        LIMIT 1
        """, {"account_id": account_id}


def build_yesterday_total_query(
    account_id: int,
    yesterday: date,
) -> Tuple[str, Dict[str, Any]]:
    """Last snapshot whose Moscow calendar date is exactly yesterday."""
    return """
        SELECT total_amount_portfolio
        FROM portfolio_snapshots
        WHERE account_id = :account_id
          AND (timezone('Europe/Moscow', snapshot_date))::date = :yesterday
        ORDER BY snapshot_date DESC
        LIMIT 1
        """, {"account_id": account_id, "yesterday": yesterday}


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
                COALESCE(ps.total_amount_portfolio, 0) AS portfolio,
                COALESCE(ps.total_amount_shares, 0) AS shares,
                COALESCE(ps.total_amount_bonds, 0) AS bonds,
                COALESCE(ps.total_amount_etf, 0) AS etf,
                COALESCE(ps.total_amount_currencies, 0) AS currencies,
                COALESCE(ps.total_amount_futures, 0) AS futures,
                COALESCE(ps.total_amount_options, 0) AS options,
                COALESCE(ps.total_amount_sp, 0) AS sp
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
            UNION ALL
            SELECT currency, 'sp', SUM(sp)
            FROM latest_snapshots GROUP BY currency
        ),
        day_norm AS (
            SELECT
                ls.currency,
                CASE lower(trim(pp.instrument_type))
                    WHEN 'futures' THEN 'future'
                    WHEN 'future' THEN 'future'
                    WHEN 'share' THEN 'share'
                    WHEN 'bond' THEN 'bond'
                    WHEN 'etf' THEN 'etf'
                    WHEN 'currency' THEN 'currency'
                    WHEN 'option' THEN 'option'
                    WHEN 'sp' THEN 'sp'
                    ELSE lower(trim(COALESCE(pp.instrument_type, '')))
                END AS instrument_type,
                pp.daily_yield
            FROM latest_snapshots ls
            INNER JOIN portfolio_positions pp
                ON pp.snapshot_id = ls.snapshot_id
        ),
        day_by_type AS (
            SELECT
                currency,
                instrument_type,
                SUM(daily_yield) AS day_delta,
                BOOL_OR(daily_yield IS NOT NULL) AS has_day_delta
            FROM day_norm
            GROUP BY currency, instrument_type
        ),
        joined AS (
            SELECT
                s.currency,
                s.instrument_type,
                COALESCE(
                    d.name,
                    CASE s.instrument_type
                        WHEN 'sp' THEN 'Структурные продукты'
                        ELSE NULL
                    END,
                    s.instrument_type,
                    'Прочее'
                ) AS asset_type,
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
        portfolio AS (
            SELECT currency, SUM(portfolio) AS portfolio_total
            FROM latest_snapshots
            GROUP BY currency
        )
        SELECT
            j.asset_type AS type,
            j.instrument_type,
            j.value,
            j.day_delta AS day_over_day_delta,
            p.currency,
            p.portfolio_total
        FROM portfolio p
        LEFT JOIN joined j ON j.currency = p.currency
        ORDER BY p.currency, j.value DESC NULLS LAST
    """
    return query, params


def list_open_accounts(db: Session, user_id: int) -> List[PortfolioAccount]:
    """Return a user's open portfolio accounts, including ones hidden from the UI."""
    return (
        db.query(PortfolioAccount)
        .filter(
            PortfolioAccount.user_id == user_id,
            PortfolioAccount.account_status == "OPEN",
        )
        .all()
    )


def list_open_account_token_types(db: Session, user_id: int) -> Dict[int, Optional[str]]:
    """token_type последнего токена открытого счёта. Нужен, чтобы понять брокера."""
    rows = db.execute(
        text(
            """
            SELECT pa.id, t.token_type
            FROM portfolio_accounts pa
            LEFT JOIN api_tokens t
              ON t.id = pa.last_token_id
             AND t.user_id = pa.user_id
            WHERE pa.user_id = :user_id
              AND UPPER(pa.account_status) = 'OPEN'
            """
        ),
        {"user_id": user_id},
    ).all()
    return {int(row[0]): (None if row[1] is None else str(row[1])) for row in rows}


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
