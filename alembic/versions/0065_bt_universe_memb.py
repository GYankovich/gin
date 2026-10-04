"""Add public.backtest_universe_membership for glass-box P1.

Revision ID: 0065_bt_universe_memb
Revises: 0064_osengine_live_ingest
"""

from alembic import op

revision = "0065_bt_universe_memb"
down_revision = "0064_osengine_live_ingest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: a prior attempt may have created the table before alembic_version
    # failed to store the >32-char revision id.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest_universe_membership (
            run_id BIGINT NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
            trade_date DATE NOT NULL,
            ticker VARCHAR(32) NOT NULL,
            source VARCHAR(64) NULL,
            filter_result VARCHAR(32) NULL,
            reject_reason TEXT NULL,
            CONSTRAINT pk_backtest_universe_membership PRIMARY KEY (run_id, trade_date, ticker)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_backtest_universe_membership_run_date
            ON backtest_universe_membership (run_id, trade_date)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_backtest_universe_membership_run_date")
    op.execute("DROP TABLE IF EXISTS backtest_universe_membership")
