"""Add crypto_universe_daily table.

Revision ID: 0034_crypto_universe_daily
Revises: 0033_candles_cache_market_schema
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0034_crypto_universe_daily"
down_revision = "0033_candles_cache_market_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS crypto_universe_daily (
                id BIGSERIAL PRIMARY KEY,
                robot_id BIGINT NOT NULL REFERENCES robots(id) ON DELETE CASCADE,
                trade_date DATE NOT NULL,
                symbol VARCHAR(32) NOT NULL,
                source VARCHAR(30) NOT NULL DEFAULT 'crypto_screening',
                filter_result VARCHAR(20),
                reject_reason TEXT,
                turnover_24h NUMERIC(20,4),
                last_price NUMERIC(20,8),
                spread_percent NUMERIC(10,6),
                meta_payload JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_crypto_universe_daily_robot_date_symbol
            ON crypto_universe_daily(robot_id, trade_date, symbol)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_crypto_universe_daily_robot_date
            ON crypto_universe_daily(robot_id, trade_date)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_crypto_universe_daily_result
            ON crypto_universe_daily(filter_result)
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP TABLE IF EXISTS crypto_universe_daily"))

