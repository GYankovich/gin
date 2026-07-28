"""Create isolated backtest storage tables.

Revision ID: 0027_backtest_storage_tables
Revises: 0026_dms_daily_universe
Create Date: 2026-04-27
"""

#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0027BacktestStorageTables [1]
#/// Исходный модуль `alembic/versions/0027_backtest_storage_tables.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0027_backtest_storage_tables"
down_revision = "0026_dms_daily_universe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.backtest_runs (
            id BIGSERIAL PRIMARY KEY,
            robot_id BIGINT NOT NULL REFERENCES {SCHEMA}.robots(id) ON DELETE CASCADE,
            requested_from TIMESTAMPTZ NOT NULL,
            requested_to TIMESTAMPTZ NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ NULL,
            status VARCHAR(20) NOT NULL,
            board VARCHAR(20) NOT NULL DEFAULT 'TQBR',
            initial_capital NUMERIC(20,4) NOT NULL,
            config_snapshot JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            execution_model JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            metrics_summary JSONB NULL,
            error_message TEXT NULL
        )
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.backtest_portfolio_snapshots (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES {SCHEMA}.backtest_runs(id) ON DELETE CASCADE,
            snapshot_time TIMESTAMPTZ NOT NULL,
            cash_balance NUMERIC(20,4) NOT NULL,
            equity NUMERIC(20,4) NOT NULL,
            positions_payload JSONB NOT NULL DEFAULT '[]'::jsonb
        )
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.backtest_signals (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES {SCHEMA}.backtest_runs(id) ON DELETE CASCADE,
            signal_time TIMESTAMPTZ NULL,
            figi VARCHAR(20) NOT NULL,
            signal_type VARCHAR(20) NOT NULL,
            price NUMERIC(20,6) NULL,
            was_executed INTEGER NOT NULL DEFAULT 0,
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.backtest_orders (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES {SCHEMA}.backtest_runs(id) ON DELETE CASCADE,
            signal_time TIMESTAMPTZ NULL,
            figi VARCHAR(20) NOT NULL,
            side VARCHAR(10) NOT NULL,
            status VARCHAR(20) NOT NULL,
            quantity NUMERIC(20,4) NOT NULL,
            requested_price NUMERIC(20,6) NULL,
            executed_price NUMERIC(20,6) NULL,
            slippage_pct NUMERIC(10,6) NOT NULL DEFAULT 0,
            commission NUMERIC(20,6) NULL,
            tax NUMERIC(20,6) NULL,
            pnl_net NUMERIC(20,6) NULL,
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
    """)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.backtest_metrics (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES {SCHEMA}.backtest_runs(id) ON DELETE CASCADE,
            total_return_percent NUMERIC(12,6) NULL,
            max_drawdown_percent NUMERIC(12,6) NULL,
            sharpe_ratio NUMERIC(12,6) NULL,
            trades_total BIGINT NOT NULL DEFAULT 0,
            win_rate_percent NUMERIC(12,6) NULL,
            avg_pnl_per_trade NUMERIC(20,6) NULL,
            final_equity NUMERIC(20,6) NULL,
            payload JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
    """)

    op.execute(f"CREATE INDEX IF NOT EXISTS ix_backtest_runs_robot_created ON {SCHEMA}.backtest_runs(robot_id, started_at DESC)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_backtest_portfolio_run_id ON {SCHEMA}.backtest_portfolio_snapshots(run_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_backtest_signals_run_id ON {SCHEMA}.backtest_signals(run_id)")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_backtest_orders_run_id ON {SCHEMA}.backtest_orders(run_id)")
    op.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS uq_backtest_metrics_run_id ON {SCHEMA}.backtest_metrics(run_id)")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.uq_backtest_metrics_run_id")
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_backtest_orders_run_id")
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_backtest_signals_run_id")
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_backtest_portfolio_run_id")
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_backtest_runs_robot_created")

    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.backtest_metrics")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.backtest_orders")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.backtest_signals")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.backtest_portfolio_snapshots")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.backtest_runs")
