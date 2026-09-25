"""Live market streams from OsEngine ingest: ticks + depth latest + heartbeat.

Revision ID: 0064_osengine_live_ingest
Revises: 0063_market_cache_leases
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0064_osengine_live_ingest"
down_revision = "0063_market_cache_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_ticks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("exchange_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=True),
        sa.Column("trade_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_market_ticks_lookup",
        "market_ticks",
        ["market", "instrument_id", "exchange_time"],
    )
    op.create_index(
        "uq_market_ticks_dedup",
        "market_ticks",
        ["market", "instrument_id", "exchange_time", "trade_id", "price", "quantity"],
        unique=True,
    )

    op.create_table(
        "market_depth_latest",
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("bids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("asks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("exchange_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("market", "instrument_id", name="pk_market_depth_latest"),
    )

    op.create_table(
        "osengine_ingest_heartbeat",
        sa.Column("stream", sa.String(length=32), primary_key=True),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subscribed_instruments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("osengine_ingest_heartbeat")
    op.drop_table("market_depth_latest")
    op.drop_index("uq_market_ticks_dedup", table_name="market_ticks")
    op.drop_index("ix_market_ticks_lookup", table_name="market_ticks")
    op.drop_table("market_ticks")
