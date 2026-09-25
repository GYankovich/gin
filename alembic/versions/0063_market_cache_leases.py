"""Market cache leases for OsEngine (and other) backtest candle TTL/GC.

Revision ID: 0063_market_cache_leases
Revises: 0062_backtest_runs_v2_robot_fk
"""

from alembic import op
import sqlalchemy as sa

revision = "0063_market_cache_leases"
down_revision = "0062_backtest_runs_v2_robot_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_cache_leases",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("instrument_id", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_market_cache_leases_run_id", "market_cache_leases", ["run_id"])
    op.create_index(
        "ix_market_cache_leases_live",
        "market_cache_leases",
        ["market", "instrument_id", "interval", "status"],
    )
    op.create_index(
        "ix_market_cache_leases_gc",
        "market_cache_leases",
        ["market", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_cache_leases_gc", table_name="market_cache_leases")
    op.drop_index("ix_market_cache_leases_live", table_name="market_cache_leases")
    op.drop_index("ix_market_cache_leases_run_id", table_name="market_cache_leases")
    op.drop_table("market_cache_leases")
