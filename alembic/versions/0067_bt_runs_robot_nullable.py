"""Ensure backtest_runs.robot_id is nullable for Lab orphan runs (SPEC-05 P0).

Revision ID: 0067_bt_runs_robot_nullable
Revises: 0066_bt_exec_events

0030 already set nullable=True; this revision is a guarded re-assert for DBs
that still have NOT NULL, plus Lab list index (user_id, started_at DESC).
"""

from alembic import op

revision = "0067_bt_runs_robot_nullable"
down_revision = "0066_bt_exec_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded: only DROP NOT NULL when the column is still non-nullable.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'backtest_runs'
                  AND column_name = 'robot_id'
                  AND is_nullable = 'NO'
            ) THEN
                ALTER TABLE backtest_runs ALTER COLUMN robot_id DROP NOT NULL;
            END IF;
        END $$;
        """
    )
    # Lab list path: all user runs ordered by started_at DESC [ref: SPEC-05 R-1].
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_backtest_runs_user_started_desc
        ON backtest_runs (user_id, started_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_backtest_runs_user_started_desc")
    # Only re-tighten if no orphan rows remain (Lab soft-bind is intentional).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM backtest_runs WHERE robot_id IS NULL LIMIT 1
            ) THEN
                ALTER TABLE backtest_runs ALTER COLUMN robot_id SET NOT NULL;
            END IF;
        END $$;
        """
    )
