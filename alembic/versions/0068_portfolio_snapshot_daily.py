"""Daily close of each portfolio account in Europe/Moscow.

Revision ID: 0068_portfolio_snapshot_daily
Revises: 0067_bt_runs_robot_nullable

One row per account per Moscow calendar day: the last snapshot of that day.
The view is evaluated on read, so today's bar moves with the latest snapshot.
"""

from alembic import op

revision = "0068_portfolio_snapshot_daily"
down_revision = "0067_bt_runs_robot_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS portfolio_snapshot_daily")
