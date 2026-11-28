"""Add portfolio_operations.ticker; backfill tickers + account/robot day stats.

Revision ID: 0097_ops_ticker_stats
Revises: 0096_portfolio_marts
"""

from alembic import op
import sqlalchemy as sa

revision = "0097_ops_ticker_stats"
down_revision = "0096_portfolio_marts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolio_operations",
        sa.Column("ticker", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_portfolio_operations_ticker",
        "portfolio_operations",
        ["ticker"],
    )

    # Prefer latest position ticker, then instrument_cache.
    op.execute(
        """
        UPDATE portfolio_operations po
        SET ticker = src.ticker
        FROM (
            SELECT DISTINCT ON (pp.figi)
                pp.figi,
                pp.ticker
            FROM portfolio_positions pp
            WHERE pp.figi IS NOT NULL
              AND pp.ticker IS NOT NULL
              AND TRIM(pp.ticker) <> ''
            ORDER BY pp.figi, pp.id DESC
        ) src
        WHERE po.figi IS NOT NULL
          AND po.figi = src.figi
          AND (po.ticker IS NULL OR TRIM(po.ticker) = '')
        """
    )
    op.execute(
        """
        UPDATE portfolio_operations po
        SET ticker = ic.ticker
        FROM instrument_cache ic
        WHERE po.figi IS NOT NULL
          AND po.figi = ic.figi
          AND ic.ticker IS NOT NULL
          AND TRIM(ic.ticker) <> ''
          AND (po.ticker IS NULL OR TRIM(po.ticker) = '')
        """
    )

    # Account stats: equity / day Δ / own_funds (FIFO W·L fills on next ops sync).
    op.execute(
        """
        INSERT INTO portfolio_account_stats (
            account_id, total_amount, currency, snapshot_id, snapshot_at,
            day_over_day_delta, day_over_day_percent,
            own_funds, gain_abs, gain_percent,
            computed_at, ops_sync_version
        )
        SELECT
            l.account_id,
            l.total_amount_portfolio,
            l.currency,
            l.snapshot_id,
            l.snapshot_date,
            CASE
                WHEN y.yesterday_total IS NULL THEN NULL
                ELSE l.total_amount_portfolio - y.yesterday_total
            END AS day_delta,
            CASE
                WHEN y.yesterday_total IS NULL OR ABS(y.yesterday_total) <= 1e-9 THEN NULL
                ELSE ((l.total_amount_portfolio - y.yesterday_total) / y.yesterday_total) * 100.0
            END AS day_pct,
            o.own_funds,
            CASE
                WHEN o.own_funds IS NULL THEN NULL
                ELSE l.total_amount_portfolio - o.own_funds
            END AS gain_abs,
            CASE
                WHEN o.own_funds IS NULL OR ABS(o.own_funds) <= 1e-9 THEN NULL
                ELSE ((l.total_amount_portfolio - o.own_funds) / o.own_funds) * 100.0
            END AS gain_pct,
            NOW(),
            0
        FROM (
            SELECT DISTINCT ON (ps.account_id)
                ps.account_id,
                ps.id AS snapshot_id,
                ps.total_amount_portfolio,
                ps.snapshot_date,
                UPPER(COALESCE(NULLIF(TRIM(ps.currency), ''), 'RUB')) AS currency,
                (timezone('Europe/Moscow', ps.snapshot_date))::date AS snap_day
            FROM portfolio_snapshots ps
            ORDER BY ps.account_id, ps.snapshot_date DESC
        ) l
        LEFT JOIN LATERAL (
            SELECT d.total_amount_portfolio AS yesterday_total
            FROM portfolio_snapshot_daily d
            WHERE d.account_id = l.account_id
              AND d.snapshot_day = l.snap_day - 1
            LIMIT 1
        ) y ON true
        LEFT JOIN LATERAL (
            SELECT SUM(signed_payment) AS own_funds
            FROM (
                SELECT
                    CASE
                        WHEN po.operation_type IN (
                            'OPERATION_TYPE_INPUT',
                            'OPERATION_TYPE_INPUT_ACQUIRING',
                            'OPERATION_TYPE_INP_MULTI'
                        )
                        AND po.status = 'OPERATION_STATE_EXECUTED'
                        AND UPPER(po.payment_currency) = l.currency
                        AND ABS(po.payment) > 1e-9
                            THEN po.payment
                        WHEN po.operation_type IN (
                            'OPERATION_TYPE_OUTPUT',
                            'OPERATION_TYPE_OUTPUT_ACQUIRING',
                            'OPERATION_TYPE_OUT_MULTI'
                        )
                        AND po.status = 'OPERATION_STATE_EXECUTED'
                        AND UPPER(po.payment_currency) = l.currency
                        AND ABS(po.payment) > 1e-9
                            THEN -ABS(po.payment)
                        WHEN po.operation_type LIKE 'BYBIT_FUND_IN%'
                        AND UPPER(po.payment_currency) = l.currency
                            THEN CASE
                                WHEN ABS(po.payment) > 1e-9 THEN po.payment
                                WHEN ABS(po.quantity) > 1e-9 THEN ABS(po.quantity)
                                ELSE NULL
                            END
                        WHEN po.operation_type LIKE 'BYBIT_FUND_OUT%'
                        AND UPPER(po.payment_currency) = l.currency
                            THEN CASE
                                WHEN ABS(po.payment) > 1e-9 THEN -ABS(po.payment)
                                WHEN ABS(po.quantity) > 1e-9 THEN -ABS(po.quantity)
                                ELSE NULL
                            END
                        WHEN po.operation_type LIKE 'BYBIT_TRANSFER_IN%'
                        AND UPPER(po.payment_currency) = l.currency
                            THEN CASE
                                WHEN ABS(po.payment) > 1e-9 THEN po.payment
                                WHEN ABS(po.quantity) > 1e-9 THEN ABS(po.quantity)
                                ELSE NULL
                            END
                        WHEN po.operation_type LIKE 'BYBIT_TRANSFER_OUT%'
                        AND UPPER(po.payment_currency) = l.currency
                            THEN CASE
                                WHEN ABS(po.payment) > 1e-9 THEN -ABS(po.payment)
                                WHEN ABS(po.quantity) > 1e-9 THEN -ABS(po.quantity)
                                ELSE NULL
                            END
                        ELSE NULL
                    END AS signed_payment
                FROM portfolio_operations po
                WHERE po.account_id = l.account_id
                  AND (
                        po.operation_type IN (
                            'OPERATION_TYPE_INPUT',
                            'OPERATION_TYPE_INPUT_ACQUIRING',
                            'OPERATION_TYPE_INP_MULTI',
                            'OPERATION_TYPE_OUTPUT',
                            'OPERATION_TYPE_OUTPUT_ACQUIRING',
                            'OPERATION_TYPE_OUT_MULTI'
                        )
                        OR po.operation_type LIKE 'BYBIT_FUND_IN%'
                        OR po.operation_type LIKE 'BYBIT_FUND_OUT%'
                        OR po.operation_type LIKE 'BYBIT_TRANSFER_IN%'
                        OR po.operation_type LIKE 'BYBIT_TRANSFER_OUT%'
                  )
            ) cash
            WHERE signed_payment IS NOT NULL
        ) o ON true
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
            computed_at = EXCLUDED.computed_at
        """
    )

    op.execute(
        """
        UPDATE portfolio_snapshot_daily d
        SET own_funds_eod = s.own_funds
        FROM portfolio_account_stats s
        WHERE d.account_id = s.account_id
          AND d.snapshot_day = (timezone('Europe/Moscow', COALESCE(s.snapshot_at, NOW())))::date
          AND s.own_funds IS NOT NULL
        """
    )

    # Historical robot day stats from fills (same close definition as fleet).
    op.execute(
        """
        INSERT INTO robot_day_stats (
            robot_id, stats_day, wins, losses, realized_pnl, fills_count, computed_at
        )
        SELECT
            f.robot_id,
            (timezone('Europe/Moscow', f.filled_at))::date AS stats_day,
            COUNT(*) FILTER (
                WHERE (UPPER(f.side) = 'SELL' OR f.kind ILIKE 'exit%') AND f.pnl > 0
            )::int AS wins,
            COUNT(*) FILTER (
                WHERE (UPPER(f.side) = 'SELL' OR f.kind ILIKE 'exit%') AND f.pnl < 0
            )::int AS losses,
            SUM(f.pnl) FILTER (
                WHERE UPPER(f.side) = 'SELL' OR f.kind ILIKE 'exit%'
            ) AS realized_pnl,
            COUNT(*)::int AS fills_count,
            NOW()
        FROM robot_fills f
        WHERE f.filled_at IS NOT NULL
        GROUP BY f.robot_id, (timezone('Europe/Moscow', f.filled_at))::date
        ON CONFLICT (robot_id, stats_day) DO UPDATE SET
            wins = EXCLUDED.wins,
            losses = EXCLUDED.losses,
            realized_pnl = EXCLUDED.realized_pnl,
            fills_count = EXCLUDED.fills_count,
            computed_at = EXCLUDED.computed_at
        """
    )


def downgrade() -> None:
    op.drop_index("ix_portfolio_operations_ticker", table_name="portfolio_operations")
    op.drop_column("portfolio_operations", "ticker")
