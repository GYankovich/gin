"""market instruments and shared historical candles

Revision ID: 0019_market_candles
Revises: 0018_add_trading_tables
Create Date: 2026-04-06

"""
from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0019_market_candles'
down_revision = '0018_add_trading_tables'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'market_instruments',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('figi', sa.String(32), nullable=False),
        sa.Column('ticker', sa.String(64), nullable=True),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('instrument_type', sa.String(32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('figi', name='uq_market_instruments_figi'),
        schema=SCHEMA,
    )
    op.create_index('ix_market_instruments_ticker', 'market_instruments', ['ticker'], schema=SCHEMA)

    op.create_table(
        'market_candles',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('figi', sa.String(32), nullable=False),
        sa.Column('candle_interval', sa.String(64), nullable=False),
        sa.Column('candle_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('open', sa.Numeric(20, 9), nullable=False),
        sa.Column('high', sa.Numeric(20, 9), nullable=False),
        sa.Column('low', sa.Numeric(20, 9), nullable=False),
        sa.Column('close', sa.Numeric(20, 9), nullable=False),
        sa.Column('volume', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.UniqueConstraint('figi', 'candle_interval', 'candle_time', name='uq_market_candles_figi_int_time'),
        schema=SCHEMA,
    )
    op.create_index(
        'ix_market_candles_figi_interval_time',
        'market_candles',
        ['figi', 'candle_interval', 'candle_time'],
        schema=SCHEMA,
    )


def downgrade():
    op.drop_index('ix_market_candles_figi_interval_time', table_name='market_candles', schema=SCHEMA)
    op.drop_table('market_candles', schema=SCHEMA)
    op.drop_index('ix_market_instruments_ticker', table_name='market_instruments', schema=SCHEMA)
    op.drop_table('market_instruments', schema=SCHEMA)
