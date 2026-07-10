"""Unify candles_cache key by market + instrument_id.

Revision ID: 0033_candles_cache_market_schema
Revises: 0032_backtest_progress_eta
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0033_candles_cache_market_schema"
down_revision = "0032_backtest_progress_eta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candles_cache",
        sa.Column("market", sa.String(length=16), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "candles_cache",
        sa.Column("instrument_id", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "candles_cache",
        sa.Column("source", sa.String(length=32), nullable=True),
        schema=SCHEMA,
    )

    # Backfill legacy MOEX rows to new discriminator columns.
    op.execute(
        sa.text(
            f"""
            UPDATE {SCHEMA}.candles_cache
               SET market = COALESCE(NULLIF(market, ''), 'moex'),
                   instrument_id = COALESCE(NULLIF(instrument_id, ''), ticker),
                   source = COALESCE(NULLIF(source, ''), 'legacy_moex')
             WHERE market IS NULL
                OR instrument_id IS NULL
                OR source IS NULL
                OR market = ''
                OR instrument_id = ''
                OR source = ''
            """
        )
    )

    op.alter_column("candles_cache", "market", nullable=False, schema=SCHEMA)
    op.alter_column("candles_cache", "instrument_id", nullable=False, schema=SCHEMA)
    op.alter_column("candles_cache", "source", nullable=False, schema=SCHEMA)

    op.execute(
        sa.text(f"DROP INDEX IF EXISTS {SCHEMA}.uq_candles_cache_ticker_interval_time")
    )
    op.execute(
        sa.text(f"DROP INDEX IF EXISTS {SCHEMA}.idx_candles_ticker_interval_time")
    )

    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_candles_cache_market_instrument_interval_time
            ON {SCHEMA}.candles_cache(market, instrument_id, interval, candle_time)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_candles_market_instrument_interval_time
            ON {SCHEMA}.candles_cache(market, instrument_id, interval, candle_time)
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"DROP INDEX IF EXISTS {SCHEMA}.uq_candles_cache_market_instrument_interval_time"
        )
    )
    op.execute(
        sa.text(
            f"DROP INDEX IF EXISTS {SCHEMA}.idx_candles_market_instrument_interval_time"
        )
    )

    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_candles_cache_ticker_interval_time
            ON {SCHEMA}.candles_cache(ticker, interval, candle_time)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_candles_ticker_interval_time
            ON {SCHEMA}.candles_cache(ticker, interval, candle_time)
            """
        )
    )

    op.drop_column("candles_cache", "source", schema=SCHEMA)
    op.drop_column("candles_cache", "instrument_id", schema=SCHEMA)
    op.drop_column("candles_cache", "market", schema=SCHEMA)
