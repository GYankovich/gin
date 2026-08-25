"""Allow v2 robot ids on backtest_runs.robot_id (drop legacy robots FK)."""

from alembic import op

revision = "0062_backtest_runs_v2_robot_fk"
down_revision = "0061_robots_v2_orders_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE backtest_runs DROP CONSTRAINT IF EXISTS backtest_runs_robot_id_fkey")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_backtest_runs_robot_id_started "
        "ON backtest_runs (robot_id, started_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_backtest_runs_robot_id_started")
