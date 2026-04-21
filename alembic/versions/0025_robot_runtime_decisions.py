"""Add runtime decision persistence tables and trade columns.

Revision ID: 0025_robot_runtime_decisions
Revises: 0024_grain_seed_only_robots
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0025_robot_runtime_decisions"
down_revision = "0024_grain_seed_only_robots"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(f"ALTER TABLE {SCHEMA}.robot_trades ADD COLUMN IF NOT EXISTS entry_price numeric(20,4)")
    op.execute(f"ALTER TABLE {SCHEMA}.robot_trades ADD COLUMN IF NOT EXISTS exit_price numeric(20,4)")
    op.execute(f"ALTER TABLE {SCHEMA}.robot_trades ADD COLUMN IF NOT EXISTS filled_quantity numeric(20,4)")
    op.execute(f"ALTER TABLE {SCHEMA}.robot_trades ADD COLUMN IF NOT EXISTS avg_fill_price numeric(20,4)")
    op.execute(f"ALTER TABLE {SCHEMA}.robot_trades ADD COLUMN IF NOT EXISTS updated_at timestamptz")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.robot_run_cycles (
            id bigserial PRIMARY KEY,
            robot_id bigint NOT NULL REFERENCES {SCHEMA}.robots(id) ON DELETE CASCADE,
            execution_log_id bigint NULL REFERENCES {SCHEMA}.robot_execution_logs(id) ON DELETE SET NULL,
            status varchar(20) NOT NULL DEFAULT 'pending',
            started_at timestamptz NOT NULL,
            finished_at timestamptz NULL,
            context jsonb NULL
        )
    """)
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_robot_run_cycles_robot_id ON {SCHEMA}.robot_run_cycles (robot_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_robot_run_cycles_exec_log_id ON {SCHEMA}.robot_run_cycles (execution_log_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_robot_run_cycles_started_at ON {SCHEMA}.robot_run_cycles (started_at)")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.robot_decisions (
            id bigserial PRIMARY KEY,
            robot_id bigint NOT NULL REFERENCES {SCHEMA}.robots(id) ON DELETE CASCADE,
            execution_log_id bigint NULL REFERENCES {SCHEMA}.robot_execution_logs(id) ON DELETE SET NULL,
            cycle_id bigint NULL REFERENCES {SCHEMA}.robot_run_cycles(id) ON DELETE SET NULL,
            figi varchar(20) NULL,
            stage varchar(50) NOT NULL,
            decision_type varchar(50) NOT NULL,
            decision varchar(50) NOT NULL,
            reason_code varchar(120) NULL,
            payload jsonb NULL,
            created_at timestamptz NOT NULL
        )
    """)
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_robot_decisions_robot_id ON {SCHEMA}.robot_decisions (robot_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_robot_decisions_cycle_id ON {SCHEMA}.robot_decisions (cycle_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_robot_decisions_created_at ON {SCHEMA}.robot_decisions (created_at)")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.robot_order_events (
            id bigserial PRIMARY KEY,
            robot_id bigint NOT NULL REFERENCES {SCHEMA}.robots(id) ON DELETE CASCADE,
            trade_id bigint NULL REFERENCES {SCHEMA}.robot_trades(id) ON DELETE SET NULL,
            order_id varchar(120) NULL,
            status varchar(50) NOT NULL,
            event_type varchar(50) NOT NULL DEFAULT 'status_update',
            payload jsonb NULL,
            created_at timestamptz NOT NULL
        )
    """)
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_robot_order_events_robot_id ON {SCHEMA}.robot_order_events (robot_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_robot_order_events_order_id ON {SCHEMA}.robot_order_events (order_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_robot_order_events_created_at ON {SCHEMA}.robot_order_events (created_at)")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.robot_backtest_runs (
            id bigserial PRIMARY KEY,
            robot_id bigint NOT NULL REFERENCES {SCHEMA}.robots(id) ON DELETE CASCADE,
            requested_from timestamptz NOT NULL,
            requested_to timestamptz NOT NULL,
            initial_capital numeric(20,4) NOT NULL,
            final_equity numeric(20,4) NOT NULL,
            total_return_percent numeric(10,4) NOT NULL,
            max_drawdown_percent numeric(10,4) NULL,
            result_payload jsonb NOT NULL,
            created_at timestamptz NOT NULL
        )
    """)
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_robot_backtest_runs_robot_id ON {SCHEMA}.robot_backtest_runs (robot_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_robot_backtest_runs_created_at ON {SCHEMA}.robot_backtest_runs (created_at)")


def downgrade():
    op.drop_index("ix_robot_backtest_runs_created_at", table_name="robot_backtest_runs", schema=SCHEMA)
    op.drop_index("ix_robot_backtest_runs_robot_id", table_name="robot_backtest_runs", schema=SCHEMA)
    op.drop_table("robot_backtest_runs", schema=SCHEMA)

    op.drop_index("ix_robot_order_events_created_at", table_name="robot_order_events", schema=SCHEMA)
    op.drop_index("ix_robot_order_events_order_id", table_name="robot_order_events", schema=SCHEMA)
    op.drop_index("ix_robot_order_events_robot_id", table_name="robot_order_events", schema=SCHEMA)
    op.drop_table("robot_order_events", schema=SCHEMA)

    op.drop_index("ix_robot_decisions_created_at", table_name="robot_decisions", schema=SCHEMA)
    op.drop_index("ix_robot_decisions_cycle_id", table_name="robot_decisions", schema=SCHEMA)
    op.drop_index("ix_robot_decisions_robot_id", table_name="robot_decisions", schema=SCHEMA)
    op.drop_table("robot_decisions", schema=SCHEMA)

    op.drop_index("ix_robot_run_cycles_started_at", table_name="robot_run_cycles", schema=SCHEMA)
    op.drop_index("ix_robot_run_cycles_exec_log_id", table_name="robot_run_cycles", schema=SCHEMA)
    op.drop_index("ix_robot_run_cycles_robot_id", table_name="robot_run_cycles", schema=SCHEMA)
    op.drop_table("robot_run_cycles", schema=SCHEMA)

    op.drop_column("robot_trades", "updated_at", schema=SCHEMA)
    op.drop_column("robot_trades", "avg_fill_price", schema=SCHEMA)
    op.drop_column("robot_trades", "filled_quantity", schema=SCHEMA)
    op.drop_column("robot_trades", "exit_price", schema=SCHEMA)
    op.drop_column("robot_trades", "entry_price", schema=SCHEMA)
