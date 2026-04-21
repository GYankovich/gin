"""add dms and daily universe tables

Revision ID: 0026_dms_daily_universe
Revises: 0025_robot_runtime_decisions
Create Date: 2026-04-21 10:00:00.000000
"""

from alembic import op
from app.core.config import settings


# revision identifiers, used by Alembic.
revision = "0026_dms_daily_universe"
down_revision = "0025_robot_runtime_decisions"
branch_labels = None
depends_on = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS {schema}.securities_static (
            ticker VARCHAR(20) PRIMARY KEY,
            shortname VARCHAR(100),
            lot_size INT,
            min_step DECIMAL(10,6),
            isin VARCHAR(20),
            status VARCHAR(10),
            updated_at TIMESTAMPTZ
        );
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS {schema}.market_snapshot (
            id BIGSERIAL PRIMARY KEY,
            snapshot_time TIMESTAMPTZ NOT NULL,
            board VARCHAR(20) NOT NULL,
            status VARCHAR(20),
            error_message TEXT,
            is_manual BOOLEAN DEFAULT FALSE,
            ttl_minutes INT DEFAULT 5,
            moex_timestamp TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS {schema}.dms_subscriptions (
            id BIGSERIAL PRIMARY KEY,
            robot_id BIGINT NOT NULL REFERENCES {schema}.robots(id) ON DELETE CASCADE,
            subscription_key VARCHAR(100) NOT NULL,
            board VARCHAR(20) NOT NULL,
            include_candles BOOLEAN DEFAULT FALSE,
            candle_interval VARCHAR(10),
            candle_depth INT DEFAULT 14,
            requested_at TIMESTAMPTZ,
            request_date DATE NOT NULL DEFAULT CURRENT_DATE,
            snapshot_hour INT,
            status VARCHAR(20),
            snapshot_id BIGINT REFERENCES {schema}.market_snapshot(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_dms_subscriptions_robot_key_date_hour
        ON {schema}.dms_subscriptions(robot_id, subscription_key, request_date, snapshot_hour);
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS {schema}.market_snapshot_data (
            id BIGSERIAL PRIMARY KEY,
            snapshot_id BIGINT NOT NULL REFERENCES {schema}.market_snapshot(id) ON DELETE CASCADE,
            ticker VARCHAR(20) NOT NULL,
            last_price DECIMAL(12,4),
            open_price DECIMAL(12,4),
            prev_price DECIMAL(12,4),
            volume_today BIGINT,
            value_today BIGINT,
            volume_lots BIGINT,
            bid DECIMAL(12,4),
            ask DECIMAL(12,4),
            spread DECIMAL(12,4),
            security_status VARCHAR(10),
            trading_status VARCHAR(20),
            num_trades BIGINT,
            min_step NUMERIC(12,6),
            issue_size NUMERIC(20,4),
            board_id VARCHAR(12),
            short_name VARCHAR(255),
            sec_name VARCHAR(255),
            isin VARCHAR(20),
            lot_size INTEGER,
            low_price NUMERIC(12,4),
            high_price NUMERIC(12,4),
            close_price NUMERIC(12,4),
            market_update_time VARCHAR(20),
            securities_payload JSONB,
            marketdata_payload JSONB
        );
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_market_snapshot_data_snapshot_ticker
        ON {schema}.market_snapshot_data(snapshot_id, ticker);
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_snapshot_data_ticker_time
        ON {schema}.market_snapshot_data(ticker, snapshot_id);
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS {schema}.market_snapshot_history (
            id BIGINT PRIMARY KEY,
            snapshot_time TIMESTAMPTZ NOT NULL,
            board VARCHAR(20) NOT NULL,
            status VARCHAR(20),
            error_message TEXT,
            is_manual BOOLEAN DEFAULT FALSE,
            ttl_minutes INT DEFAULT 5,
            moex_timestamp TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS {schema}.market_snapshot_data_history (
            id BIGINT PRIMARY KEY,
            snapshot_id BIGINT NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            last_price DECIMAL(12,4),
            open_price DECIMAL(12,4),
            prev_price DECIMAL(12,4),
            volume_today BIGINT,
            value_today BIGINT,
            volume_lots BIGINT,
            bid DECIMAL(12,4),
            ask DECIMAL(12,4),
            spread DECIMAL(12,4),
            security_status VARCHAR(10),
            trading_status VARCHAR(20),
            num_trades BIGINT,
            min_step NUMERIC(12,6),
            issue_size NUMERIC(20,4),
            board_id VARCHAR(12),
            short_name VARCHAR(255),
            sec_name VARCHAR(255),
            isin VARCHAR(20),
            lot_size INTEGER,
            low_price NUMERIC(12,4),
            high_price NUMERIC(12,4),
            close_price NUMERIC(12,4),
            market_update_time VARCHAR(20),
            securities_payload JSONB,
            marketdata_payload JSONB
        );
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_snapshot_data_history_snapshot_ticker
        ON {schema}.market_snapshot_data_history(snapshot_id, ticker);
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS {schema}.candles_cache (
            id BIGSERIAL PRIMARY KEY,
            ticker VARCHAR(20) NOT NULL,
            interval VARCHAR(10) NOT NULL,
            candle_time TIMESTAMPTZ NOT NULL,
            open DECIMAL(12,4),
            high DECIMAL(12,4),
            low DECIMAL(12,4),
            close DECIMAL(12,4),
            volume BIGINT,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_candles_cache_ticker_interval_time
        ON {schema}.candles_cache(ticker, interval, candle_time);
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_candles_ticker_interval_time
        ON {schema}.candles_cache(ticker, interval, candle_time);
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS {schema}.daily_universe (
            id BIGSERIAL PRIMARY KEY,
            robot_id BIGINT NOT NULL REFERENCES {schema}.robots(id) ON DELETE CASCADE,
            trade_date DATE NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            source VARCHAR(30) NOT NULL,
            filter_result VARCHAR(20),
            reject_reason TEXT,
            snapshot_id BIGINT REFERENCES {schema}.market_snapshot(id) ON DELETE SET NULL,
            price_at_filter DECIMAL(12,4),
            volume_at_filter BIGINT,
            atr_value DECIMAL(12,4),
            gap_percent DECIMAL(6,3),
            applied_filters TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """.format(schema=SCHEMA)
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_universe_robot_date_ticker
        ON {schema}.daily_universe(robot_id, trade_date, ticker);
        """.format(schema=SCHEMA)
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_universe_robot_date ON {schema}.daily_universe(robot_id, trade_date);".format(schema=SCHEMA))
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_universe_result ON {schema}.daily_universe(filter_result);".format(schema=SCHEMA))
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_universe_snapshot ON {schema}.daily_universe(snapshot_id);".format(schema=SCHEMA))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS {schema}.daily_universe;".format(schema=SCHEMA))
    op.execute("DROP TABLE IF EXISTS {schema}.candles_cache;".format(schema=SCHEMA))
    op.execute("DROP TABLE IF EXISTS {schema}.market_snapshot_data_history;".format(schema=SCHEMA))
    op.execute("DROP TABLE IF EXISTS {schema}.market_snapshot_history;".format(schema=SCHEMA))
    op.execute("DROP TABLE IF EXISTS {schema}.market_snapshot_data;".format(schema=SCHEMA))
    op.execute("DROP TABLE IF EXISTS {schema}.dms_subscriptions;".format(schema=SCHEMA))
    op.execute("DROP TABLE IF EXISTS {schema}.market_snapshot;".format(schema=SCHEMA))
    op.execute("DROP TABLE IF EXISTS {schema}.securities_static;".format(schema=SCHEMA))
