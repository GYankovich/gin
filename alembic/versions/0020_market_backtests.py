"""store market backtest runs

Revision ID: 0020_market_backtests
Revises: 0019_market_candles
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0020_market_backtests"
down_revision = "0019_market_candles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "market_backtests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("figi", sa.String(32), nullable=False),
        sa.Column("candle_interval", sa.String(64), nullable=False),
        sa.Column("strategy", sa.String(64), nullable=False),
        sa.Column("from_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("initial_capital", sa.Numeric(20, 4), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_market_backtests_user_created", "market_backtests", ["user_id", "created_at"], schema=SCHEMA)
    op.create_index("ix_market_backtests_strategy", "market_backtests", ["strategy"], schema=SCHEMA)
    op.create_index("ix_market_backtests_figi", "market_backtests", ["figi"], schema=SCHEMA)


def downgrade():
    op.drop_index("ix_market_backtests_figi", table_name="market_backtests", schema=SCHEMA)
    op.drop_index("ix_market_backtests_strategy", table_name="market_backtests", schema=SCHEMA)
    op.drop_index("ix_market_backtests_user_created", table_name="market_backtests", schema=SCHEMA)
    op.drop_table("market_backtests", schema=SCHEMA)
