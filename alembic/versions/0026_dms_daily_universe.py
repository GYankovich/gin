"""add dms and daily universe tables

Revision ID: 0026_dms_daily_universe
Revises: 0025_robot_runtime_decisions
Create Date: 2026-04-21 10:00:00.000000
"""

#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0026DmsDailyUniverse [1]
#/// Исходный модуль `alembic/versions/0026_dms_daily_universe.py` — автоматическая разметка для Obsidian Source Scanner.

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
        CREATE TABLE IF NOT EXISTS securities_static (
            ticker VARCHAR(20) PRIMARY KEY,
            shortname VARCHAR(100),
            lot_size INT,
            min_step DECIMAL(10,6),
            isin VARCHAR(20),
            status VARCHAR(10),
            updated_at TIMESTAMPTZ
        );
        """.format()
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_snapshot (
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
        """.format()
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dms_subscriptions (
            id BIGSERIAL PRIMARY KEY,
            robot_id BIGINT NOT NULL REFERENCES robots(id) ON DELETE CASCADE,
            subscription_key VARCHAR(100) NOT NULL,
            board VARCHAR(20) NOT NULL,
            include_candles BOOLEAN DEFAULT FALSE,
            candle_interval VARCHAR(10),
            candle_depth INT DEFAULT 14,
            requested_at TIMESTAMPTZ,
            request_date DATE NOT NULL DEFAULT CURRENT_DATE,
            snapshot_hour INT,
            status VARCHAR(20),
            snapshot_id BIGINT REFERENCES market_snapshot(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """.format()
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_dms_subscriptions_robot_key_date_hour
        ON dms_subscriptions(robot_id, subscription_key, request_date, snapshot_hour);
        """.format()
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_snapshot_data (
            id BIGSERIAL PRIMARY KEY,
            snapshot_id BIGINT NOT NULL REFERENCES market_snapshot(id) ON DELETE CASCADE,
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
            sec_type VARCHAR(3),
            list_level INTEGER,
            face_value NUMERIC(20,6),
            board_name VARCHAR(381),
            decimals INTEGER,
            remarks VARCHAR(255),
            market_code VARCHAR(12),
            instr_id VARCHAR(12),
            sector_id VARCHAR(12),
            face_unit VARCHAR(12),
            prev_date DATE,
            lat_name VARCHAR(255),
            reg_number VARCHAR(90),
            currency_id VARCHAR(12),
            settle_date DATE,
            lot_size INTEGER,
            low_price NUMERIC(12,4),
            high_price NUMERIC(12,4),
            close_price NUMERIC(12,4),
            prev_wa_price NUMERIC(12,4),
            prev_legal_close_price NUMERIC(12,4),
            value NUMERIC(20,4),
            value_usd NUMERIC(20,4),
            wa_price NUMERIC(12,4),
            last_change NUMERIC(12,4),
            last_change_prcnt NUMERIC(12,4),
            market_price_today NUMERIC(12,4),
            market_price NUMERIC(12,4),
            last_to_prev_price NUMERIC(12,4),
            market_update_time VARCHAR(20),
            val_today_rur BIGINT,
            trading_session VARCHAR(3),
            seq_num BIGINT,
            sys_time TIMESTAMPTZ,
            issue_capitalization NUMERIC(20,4),
            trend_issue_capitalization NUMERIC(20,4),
            securities_payload JSONB,
            marketdata_payload JSONB
        );
        """.format()
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_market_snapshot_data_snapshot_ticker
        ON market_snapshot_data(snapshot_id, ticker);
        """.format()
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_snapshot_data_ticker_time
        ON market_snapshot_data(ticker, snapshot_id);
        """.format()
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_snapshot_history (
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
        """.format()
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_snapshot_data_history (
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
            sec_type VARCHAR(3),
            list_level INTEGER,
            face_value NUMERIC(20,6),
            board_name VARCHAR(381),
            decimals INTEGER,
            remarks VARCHAR(255),
            market_code VARCHAR(12),
            instr_id VARCHAR(12),
            sector_id VARCHAR(12),
            face_unit VARCHAR(12),
            prev_date DATE,
            lat_name VARCHAR(255),
            reg_number VARCHAR(90),
            currency_id VARCHAR(12),
            settle_date DATE,
            lot_size INTEGER,
            low_price NUMERIC(12,4),
            high_price NUMERIC(12,4),
            close_price NUMERIC(12,4),
            prev_wa_price NUMERIC(12,4),
            prev_legal_close_price NUMERIC(12,4),
            value NUMERIC(20,4),
            value_usd NUMERIC(20,4),
            wa_price NUMERIC(12,4),
            last_change NUMERIC(12,4),
            last_change_prcnt NUMERIC(12,4),
            market_price_today NUMERIC(12,4),
            market_price NUMERIC(12,4),
            last_to_prev_price NUMERIC(12,4),
            market_update_time VARCHAR(20),
            val_today_rur BIGINT,
            trading_session VARCHAR(3),
            seq_num BIGINT,
            sys_time TIMESTAMPTZ,
            issue_capitalization NUMERIC(20,4),
            trend_issue_capitalization NUMERIC(20,4),
            securities_payload JSONB,
            marketdata_payload JSONB
        );
        """.format()
    )
    # Backward compatibility: if table already exists, add newly introduced columns.
    op.execute(
        """
        ALTER TABLE market_snapshot_data
            ADD COLUMN IF NOT EXISTS sec_type VARCHAR(3),
            ADD COLUMN IF NOT EXISTS list_level INTEGER,
            ADD COLUMN IF NOT EXISTS prev_wa_price NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS prev_legal_close_price NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS face_value NUMERIC(20,6),
            ADD COLUMN IF NOT EXISTS board_name VARCHAR(381),
            ADD COLUMN IF NOT EXISTS decimals INTEGER,
            ADD COLUMN IF NOT EXISTS remarks VARCHAR(255),
            ADD COLUMN IF NOT EXISTS market_code VARCHAR(12),
            ADD COLUMN IF NOT EXISTS instr_id VARCHAR(12),
            ADD COLUMN IF NOT EXISTS sector_id VARCHAR(12),
            ADD COLUMN IF NOT EXISTS face_unit VARCHAR(12),
            ADD COLUMN IF NOT EXISTS prev_date DATE,
            ADD COLUMN IF NOT EXISTS lat_name VARCHAR(255),
            ADD COLUMN IF NOT EXISTS reg_number VARCHAR(90),
            ADD COLUMN IF NOT EXISTS currency_id VARCHAR(12),
            ADD COLUMN IF NOT EXISTS settle_date DATE,
            ADD COLUMN IF NOT EXISTS value NUMERIC(20,4),
            ADD COLUMN IF NOT EXISTS value_usd NUMERIC(20,4),
            ADD COLUMN IF NOT EXISTS wa_price NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS last_change NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS last_change_prcnt NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS market_price_today NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS market_price NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS last_to_prev_price NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS val_today_rur BIGINT,
            ADD COLUMN IF NOT EXISTS trading_session VARCHAR(3),
            ADD COLUMN IF NOT EXISTS seq_num BIGINT,
            ADD COLUMN IF NOT EXISTS sys_time TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS issue_capitalization NUMERIC(20,4),
            ADD COLUMN IF NOT EXISTS trend_issue_capitalization NUMERIC(20,4);
        """.format()
    )
    op.execute(
        """
        ALTER TABLE market_snapshot_data_history
            ADD COLUMN IF NOT EXISTS sec_type VARCHAR(3),
            ADD COLUMN IF NOT EXISTS list_level INTEGER,
            ADD COLUMN IF NOT EXISTS prev_wa_price NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS prev_legal_close_price NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS face_value NUMERIC(20,6),
            ADD COLUMN IF NOT EXISTS board_name VARCHAR(381),
            ADD COLUMN IF NOT EXISTS decimals INTEGER,
            ADD COLUMN IF NOT EXISTS remarks VARCHAR(255),
            ADD COLUMN IF NOT EXISTS market_code VARCHAR(12),
            ADD COLUMN IF NOT EXISTS instr_id VARCHAR(12),
            ADD COLUMN IF NOT EXISTS sector_id VARCHAR(12),
            ADD COLUMN IF NOT EXISTS face_unit VARCHAR(12),
            ADD COLUMN IF NOT EXISTS prev_date DATE,
            ADD COLUMN IF NOT EXISTS lat_name VARCHAR(255),
            ADD COLUMN IF NOT EXISTS reg_number VARCHAR(90),
            ADD COLUMN IF NOT EXISTS currency_id VARCHAR(12),
            ADD COLUMN IF NOT EXISTS settle_date DATE,
            ADD COLUMN IF NOT EXISTS value NUMERIC(20,4),
            ADD COLUMN IF NOT EXISTS value_usd NUMERIC(20,4),
            ADD COLUMN IF NOT EXISTS wa_price NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS last_change NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS last_change_prcnt NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS market_price_today NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS market_price NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS last_to_prev_price NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS val_today_rur BIGINT,
            ADD COLUMN IF NOT EXISTS trading_session VARCHAR(3),
            ADD COLUMN IF NOT EXISTS seq_num BIGINT,
            ADD COLUMN IF NOT EXISTS sys_time TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS issue_capitalization NUMERIC(20,4),
            ADD COLUMN IF NOT EXISTS trend_issue_capitalization NUMERIC(20,4);
        """.format()
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_snapshot_data_history_snapshot_ticker
        ON market_snapshot_data_history(snapshot_id, ticker);
        """.format()
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candles_cache (
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
        """.format()
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_candles_cache_ticker_interval_time
        ON candles_cache(ticker, interval, candle_time);
        """.format()
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_candles_ticker_interval_time
        ON candles_cache(ticker, interval, candle_time);
        """.format()
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_universe (
            id BIGSERIAL PRIMARY KEY,
            robot_id BIGINT NOT NULL REFERENCES robots(id) ON DELETE CASCADE,
            trade_date DATE NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            source VARCHAR(30) NOT NULL,
            filter_result VARCHAR(20),
            reject_reason TEXT,
            snapshot_id BIGINT REFERENCES market_snapshot(id) ON DELETE SET NULL,
            price_at_filter DECIMAL(12,4),
            volume_at_filter BIGINT,
            atr_value DECIMAL(12,4),
            gap_percent DECIMAL(6,3),
            applied_filters TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """.format()
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_universe_robot_date_ticker
        ON daily_universe(robot_id, trade_date, ticker);
        """.format()
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_universe_robot_date ON daily_universe(robot_id, trade_date);".format())
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_universe_result ON daily_universe(filter_result);".format())
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_universe_snapshot ON daily_universe(snapshot_id);".format())


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS daily_universe;".format())
    op.execute("DROP TABLE IF EXISTS candles_cache;".format())
    op.execute("DROP TABLE IF EXISTS market_snapshot_data_history;".format())
    op.execute("DROP TABLE IF EXISTS market_snapshot_history;".format())
    op.execute("DROP TABLE IF EXISTS market_snapshot_data;".format())
    op.execute("DROP TABLE IF EXISTS dms_subscriptions;".format())
    op.execute("DROP TABLE IF EXISTS market_snapshot;".format())
    op.execute("DROP TABLE IF EXISTS securities_static;".format())
