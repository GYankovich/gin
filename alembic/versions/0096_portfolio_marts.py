"""portfolio_snapshot_daily TABLE + portfolio_account_stats + robot_day_stats.

Revision ID: 0096_portfolio_marts
Revises: 0095_drop_mirrors

Replaces the expensive daily VIEW with a table (same name/columns + day_delta),
adds account KPI rollup and robot day W/L rollup.
"""

from alembic import op

revision = "0096_portfolio_marts"
down_revision = "0095_drop_mirrors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS portfolio_snapshot_daily")

    op.execute(
        """
        CREATE TABLE portfolio_snapshot_daily (
            id BIGINT NOT NULL,
            account_id BIGINT NOT NULL REFERENCES portfolio_accounts(id) ON DELETE CASCADE,
            snapshot_day DATE NOT NULL,
            snapshot_date TIMESTAMPTZ NOT NULL,
            total_amount_portfolio DOUBLE PRECISION,
            daily_yield DOUBLE PRECISION,
            expected_yield DOUBLE PRECISION,
            currency VARCHAR(16),
            day_delta DOUBLE PRECISION,
            own_funds_eod DOUBLE PRECISION,
            PRIMARY KEY (account_id, snapshot_day)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_portfolio_snapshot_daily_day
            ON portfolio_snapshot_daily (snapshot_day)
        """
    )
    op.execute(
        """
        INSERT INTO portfolio_snapshot_daily (
            id, account_id, snapshot_day, snapshot_date,
            total_amount_portfolio, daily_yield, expected_yield, currency
        )
        SELECT DISTINCT ON (
            ps.account_id,
            (timezone('Europe/Moscow', ps.snapshot_date))::date
        )
            ps.id,
            ps.account_id,
            (timezone('Europe/Moscow', ps.snapshot_date))::date AS snapshot_day,
            ps.snapshot_date,
            ps.total_amount_portfolio,
            ps.daily_yield,
            ps.expected_yield,
            ps.currency
        FROM portfolio_snapshots ps
        ORDER BY
            ps.account_id,
            (timezone('Europe/Moscow', ps.snapshot_date))::date,
            ps.snapshot_date DESC
        """
    )
    op.execute(
        """
        UPDATE portfolio_snapshot_daily d
        SET day_delta = d.total_amount_portfolio - p.total_amount_portfolio
        FROM portfolio_snapshot_daily p
        WHERE p.account_id = d.account_id
          AND p.snapshot_day = d.snapshot_day - 1
        """
    )

    op.execute(
        """
        CREATE TABLE portfolio_account_stats (
            account_id BIGINT PRIMARY KEY
                REFERENCES portfolio_accounts(id) ON DELETE CASCADE,
            total_amount DOUBLE PRECISION,
            currency VARCHAR(16),
            snapshot_id BIGINT,
            snapshot_at TIMESTAMPTZ,
            day_over_day_delta DOUBLE PRECISION,
            day_over_day_percent DOUBLE PRECISION,
            own_funds DOUBLE PRECISION,
            gain_abs DOUBLE PRECISION,
            gain_percent DOUBLE PRECISION,
            wins INTEGER,
            losses INTEGER,
            win_rate_percent DOUBLE PRECISION,
            first_input_at TIMESTAMPTZ,
            avg_monthly_roi_percent DOUBLE PRECISION,
            positions_count INTEGER,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ops_sync_version BIGINT NOT NULL DEFAULT 0
        )
        """
    )

    op.execute(
        """
        CREATE TABLE robot_day_stats (
            robot_id BIGINT NOT NULL REFERENCES robots(id) ON DELETE CASCADE,
            stats_day DATE NOT NULL,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            realized_pnl DOUBLE PRECISION,
            fills_count INTEGER NOT NULL DEFAULT 0,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (robot_id, stats_day)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_robot_day_stats_day
            ON robot_day_stats (stats_day)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS robot_day_stats")
    op.execute("DROP TABLE IF EXISTS portfolio_account_stats")
    op.execute("DROP TABLE IF EXISTS portfolio_snapshot_daily")
    op.execute(
        """
        CREATE OR REPLACE VIEW portfolio_snapshot_daily AS
        SELECT DISTINCT ON (
            ps.account_id,
            (timezone('Europe/Moscow', ps.snapshot_date))::date
        )
            ps.id,
            ps.account_id,
            (timezone('Europe/Moscow', ps.snapshot_date))::date AS snapshot_day,
            ps.snapshot_date,
            ps.total_amount_portfolio,
            ps.daily_yield,
            ps.expected_yield,
            ps.currency
        FROM portfolio_snapshots ps
        ORDER BY
            ps.account_id,
            (timezone('Europe/Moscow', ps.snapshot_date))::date,
            ps.snapshot_date DESC
        """
    )
