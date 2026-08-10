"""Add bybit_funding_history table.

Revision ID: 0035_bybit_funding_history
Revises: 0034_crypto_universe_daily
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0035_bybit_funding_history"
down_revision = "0034_crypto_universe_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS bybit_funding_history (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(32) NOT NULL,
                funding_time TIMESTAMPTZ NOT NULL,
                funding_rate NUMERIC(12, 8) NOT NULL,
                instrument_category VARCHAR(16) NOT NULL DEFAULT 'linear',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_bybit_funding_history_symbol_time_category
            ON bybit_funding_history(symbol, funding_time, instrument_category)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_bybit_funding_history_symbol_time
            ON bybit_funding_history(symbol, funding_time)
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP TABLE IF EXISTS bybit_funding_history"))
