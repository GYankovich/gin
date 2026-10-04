"""Add public.backtest_execution_events for glass-box P2 intent lifecycle.

Revision ID: 0066_bt_exec_events
Revises: 0065_bt_universe_memb
"""

from alembic import op

revision = "0066_bt_exec_events"
down_revision = "0065_bt_universe_memb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent in case a partial prior apply created objects without version bump.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest_execution_events (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
            event_time TIMESTAMPTZ NOT NULL,
            intent_id VARCHAR(64) NOT NULL,
            cycle_id VARCHAR(64) NULL,
            ticker VARCHAR(32) NOT NULL,
            side VARCHAR(10) NULL,
            kind VARCHAR(32) NULL,
            status VARCHAR(20) NOT NULL,
            reason VARCHAR(64) NULL,
            reject_reason VARCHAR(64) NULL,
            quantity NUMERIC(20, 4) NULL,
            price NUMERIC(20, 8) NULL,
            trade_id BIGINT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_backtest_execution_events_run_id
            ON backtest_execution_events (run_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_backtest_execution_events_run_cycle
            ON backtest_execution_events (run_id, cycle_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_backtest_execution_events_run_intent
            ON backtest_execution_events (run_id, intent_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_backtest_execution_events_run_intent")
    op.execute("DROP INDEX IF EXISTS ix_backtest_execution_events_run_cycle")
    op.execute("DROP INDEX IF EXISTS ix_backtest_execution_events_run_id")
    op.execute("DROP TABLE IF EXISTS backtest_execution_events")
