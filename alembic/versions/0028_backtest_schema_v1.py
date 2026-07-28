"""Create dedicated backtest schema and v1 tables.

Revision ID: 0028_backtest_schema_v1
Revises: 0027_backtest_storage_tables
Create Date: 2026-04-29
"""

#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0028BacktestSchemaV1 [1]
#/// Исходный модуль `alembic/versions/0028_backtest_schema_v1.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op


revision = "0028_backtest_schema_v1"
down_revision = "0027_backtest_storage_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS backtest")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest.backtest_runs (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL DEFAULT 'history-backtest',
            description TEXT NULL,
            robot_config_id BIGINT NOT NULL,
            robot_config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            date_from DATE NOT NULL,
            date_to DATE NOT NULL,
            initial_capital NUMERIC(14,2) NOT NULL DEFAULT 100000.00,
            commission_percent NUMERIC(5,4) NOT NULL DEFAULT 0.05,
            slippage_percent NUMERIC(5,4) NOT NULL DEFAULT 0.1,
            lot_fixed_fee NUMERIC(8,2) NOT NULL DEFAULT 0.0,
            execution_model VARCHAR(20) NOT NULL DEFAULT 'NEXT_BAR_OPEN',
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            progress_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
            started_at TIMESTAMPTZ NULL,
            completed_at TIMESTAMPTZ NULL,
            created_by VARCHAR(50) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest.backtest_daily_universe (
            id BIGSERIAL PRIMARY KEY,
            backtest_run_id BIGINT NOT NULL REFERENCES backtest.backtest_runs(id) ON DELETE CASCADE,
            trade_date DATE NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            source VARCHAR(30) NOT NULL,
            filter_result VARCHAR(20) NULL,
            reject_reason TEXT NULL,
            snapshot_id BIGINT NULL,
            price_at_filter NUMERIC(12,4) NULL,
            volume_at_filter BIGINT NULL,
            atr_value NUMERIC(12,4) NULL,
            gap_percent NUMERIC(6,3) NULL,
            applied_filters JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(backtest_run_id, trade_date, ticker)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest.backtest_signals (
            id BIGSERIAL PRIMARY KEY,
            backtest_run_id BIGINT NOT NULL REFERENCES backtest.backtest_runs(id) ON DELETE CASCADE,
            trade_date DATE NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            direction VARCHAR(10) NOT NULL,
            signal_time TIMESTAMPTZ NOT NULL,
            price_at_signal NUMERIC(12,4) NULL,
            quantity_lots INT NULL,
            stop_loss NUMERIC(12,4) NULL,
            take_profit NUMERIC(12,4) NULL,
            reason VARCHAR(50) NOT NULL DEFAULT 'GENERATED',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest.backtest_orders (
            id BIGSERIAL PRIMARY KEY,
            backtest_run_id BIGINT NOT NULL REFERENCES backtest.backtest_runs(id) ON DELETE CASCADE,
            signal_id BIGINT NULL REFERENCES backtest.backtest_signals(id) ON DELETE SET NULL,
            ticker VARCHAR(20) NOT NULL,
            direction VARCHAR(10) NOT NULL,
            order_type VARCHAR(20) NOT NULL DEFAULT 'LIMIT',
            limit_price NUMERIC(12,4) NULL,
            requested_quantity INT NULL,
            executed_quantity INT NOT NULL DEFAULT 0,
            avg_execution_price NUMERIC(12,4) NULL,
            slippage_cost NUMERIC(12,4) NOT NULL DEFAULT 0,
            commission_cost NUMERIC(12,4) NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            placed_at TIMESTAMPTZ NULL,
            filled_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest.backtest_trades (
            id BIGSERIAL PRIMARY KEY,
            backtest_run_id BIGINT NOT NULL REFERENCES backtest.backtest_runs(id) ON DELETE CASCADE,
            order_id BIGINT NULL REFERENCES backtest.backtest_orders(id) ON DELETE SET NULL,
            ticker VARCHAR(20) NOT NULL,
            direction VARCHAR(10) NOT NULL,
            quantity INT NOT NULL,
            price NUMERIC(12,4) NOT NULL,
            commission NUMERIC(12,4) NOT NULL DEFAULT 0,
            trade_time TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest.backtest_positions (
            id BIGSERIAL PRIMARY KEY,
            backtest_run_id BIGINT NOT NULL REFERENCES backtest.backtest_runs(id) ON DELETE CASCADE,
            trade_date DATE NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            quantity INT NOT NULL,
            avg_entry_price NUMERIC(12,4) NULL,
            current_price NUMERIC(12,4) NULL,
            unrealized_pnl NUMERIC(12,4) NULL,
            realized_pnl NUMERIC(12,4) NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(backtest_run_id, trade_date, ticker)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest.backtest_equity_curve (
            id BIGSERIAL PRIMARY KEY,
            backtest_run_id BIGINT NOT NULL REFERENCES backtest.backtest_runs(id) ON DELETE CASCADE,
            trade_date DATE NOT NULL,
            cash NUMERIC(14,2) NULL,
            positions_value NUMERIC(14,2) NULL,
            total_equity NUMERIC(14,2) NULL,
            daily_pnl NUMERIC(12,4) NULL,
            daily_return_percent NUMERIC(8,4) NULL,
            commission_paid NUMERIC(12,4) NOT NULL DEFAULT 0,
            slippage_paid NUMERIC(12,4) NOT NULL DEFAULT 0,
            trades_count INT NOT NULL DEFAULT 0,
            drawdown NUMERIC(8,4) NULL,
            drawdown_percent NUMERIC(6,2) NULL,
            UNIQUE(backtest_run_id, trade_date)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest.backtest_metrics (
            id BIGSERIAL PRIMARY KEY,
            backtest_run_id BIGINT NOT NULL UNIQUE REFERENCES backtest.backtest_runs(id) ON DELETE CASCADE,
            start_date DATE NULL,
            end_date DATE NULL,
            trading_days INT NULL,
            total_trades INT NULL,
            winning_trades INT NULL,
            losing_trades INT NULL,
            win_rate NUMERIC(5,2) NULL,
            total_return_percent NUMERIC(8,2) NULL,
            annualized_return_percent NUMERIC(8,2) NULL,
            max_drawdown_percent NUMERIC(6,2) NULL,
            max_drawdown_duration INT NULL,
            sharpe_ratio NUMERIC(6,2) NULL,
            sortino_ratio NUMERIC(6,2) NULL,
            calmar_ratio NUMERIC(6,2) NULL,
            volatility_annual NUMERIC(6,2) NULL,
            initial_capital NUMERIC(14,2) NULL,
            final_equity NUMERIC(14,2) NULL,
            gross_profit NUMERIC(14,2) NULL,
            gross_loss NUMERIC(14,2) NULL,
            total_commission NUMERIC(14,2) NULL,
            total_slippage NUMERIC(14,2) NULL,
            net_profit NUMERIC(14,2) NULL,
            profit_factor NUMERIC(6,2) NULL,
            profit_per_trade NUMERIC(12,4) NULL,
            avg_win NUMERIC(12,4) NULL,
            avg_loss NUMERIC(12,4) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest.backtest_comparisons (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(200) NULL,
            base_run_id BIGINT NOT NULL REFERENCES backtest.backtest_runs(id) ON DELETE CASCADE,
            compare_run_id BIGINT NOT NULL REFERENCES backtest.backtest_runs(id) ON DELETE CASCADE,
            config_diff JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS backtest.backtest_comparisons")
    op.execute("DROP TABLE IF EXISTS backtest.backtest_metrics")
    op.execute("DROP TABLE IF EXISTS backtest.backtest_equity_curve")
    op.execute("DROP TABLE IF EXISTS backtest.backtest_positions")
    op.execute("DROP TABLE IF EXISTS backtest.backtest_trades")
    op.execute("DROP TABLE IF EXISTS backtest.backtest_orders")
    op.execute("DROP TABLE IF EXISTS backtest.backtest_signals")
    op.execute("DROP TABLE IF EXISTS backtest.backtest_daily_universe")
    op.execute("DROP TABLE IF EXISTS backtest.backtest_runs")
    op.execute("DROP SCHEMA IF EXISTS backtest")

