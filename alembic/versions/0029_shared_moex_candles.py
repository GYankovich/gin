"""Shared MOEX OHLCV by TICKER + background candle load jobs [ref: ARCH-01].

Revision ID: 0029_shared_moex_candles
Revises: 0028_backtest_schema_v1
Create Date: 2026-05-12
"""

#///EPIC Platform.ITEM Migrations.TOPIC SharedMoexCandlesAndJobs [1]

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0029_shared_moex_candles"
down_revision = "0028_backtest_schema_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shared_market_candles",
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("board", sa.String(16), nullable=False, server_default="TQBR"),
        sa.Column("interval", sa.String(32), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(20, 9), nullable=False),
        sa.Column("high", sa.Numeric(20, 9), nullable=False),
        sa.Column("low", sa.Numeric(20, 9), nullable=False),
        sa.Column("close", sa.Numeric(20, 9), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="MOEX_ISS"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("ticker", "board", "interval", "bucket_start", name="pk_shared_market_candles"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_shared_market_candles_range",
        "shared_market_candles",
        ["ticker", "board", "interval", "bucket_start"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "candle_load_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("board", sa.String(16), nullable=False, server_default="TQBR"),
        sa.Column("interval", sa.String(32), nullable=False),
        sa.Column("from_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tickers", ARRAY(sa.Text()), nullable=False),
        sa.Column("tickers_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tickers_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bars_written", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("progress_percent", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("eta_seconds", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_candle_load_jobs_idempotency"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_candle_load_jobs_status_created",
        "candle_load_jobs",
        ["status", "created_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_candle_load_jobs_status_created", table_name="candle_load_jobs", schema=SCHEMA)
    op.drop_table("candle_load_jobs", schema=SCHEMA)
    op.drop_index("ix_shared_market_candles_range", table_name="shared_market_candles", schema=SCHEMA)
    op.drop_table("shared_market_candles", schema=SCHEMA)
