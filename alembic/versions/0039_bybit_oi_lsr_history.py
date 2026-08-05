"""Add bybit_open_interest_history and bybit_lsr_history tables.

Revision ID: 0039_bybit_oi_lsr_history
Revises: 0038_dictionary_token_type_bybit
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0039_bybit_oi_lsr_history"
down_revision = "0038_dictionary_token_type_bybit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS bybit_open_interest_history (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(32) NOT NULL,
                snapshot_time TIMESTAMPTZ NOT NULL,
                open_interest_usd NUMERIC(20, 4) NOT NULL,
                instrument_category VARCHAR(16) NOT NULL DEFAULT 'linear',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_bybit_oi_history_symbol_time_category
            ON bybit_open_interest_history(symbol, snapshot_time, instrument_category)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_bybit_oi_history_symbol_time
            ON bybit_open_interest_history(symbol, snapshot_time)
            """
        )
    )

    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS bybit_lsr_history (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(32) NOT NULL,
                snapshot_time TIMESTAMPTZ NOT NULL,
                long_ratio NUMERIC(12, 8) NOT NULL,
                short_ratio NUMERIC(12, 8) NOT NULL,
                instrument_category VARCHAR(16) NOT NULL DEFAULT 'linear',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_bybit_lsr_history_symbol_time_category
            ON bybit_lsr_history(symbol, snapshot_time, instrument_category)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_bybit_lsr_history_symbol_time
            ON bybit_lsr_history(symbol, snapshot_time)
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP TABLE IF EXISTS bybit_lsr_history"))
    op.execute(sa.text(f"DROP TABLE IF EXISTS bybit_open_interest_history"))
