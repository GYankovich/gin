"""add portfolio tables

Revision ID: 0003_add_portfolio_tables
Revises: 0002_create_api_tokens
Create Date: 2026-03-03 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0003_add_portfolio_tables'
down_revision = '0002_create_api_tokens'
branch_labels = None
depends_on = None


def upgrade():
    # Portfolio Accounts
    op.create_table(
        'portfolio_accounts',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('account_id', sa.String(50), nullable=False, unique=True),
        sa.Column('account_type', sa.String(50), nullable=False),
        sa.Column('account_name', sa.String(255), nullable=True),
        sa.Column('account_status', sa.String(50), nullable=False),
        sa.Column('opened_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('access_level', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], [f'{SCHEMA}.user.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'account_id', name='uq_user_account'),
        schema=SCHEMA,
    )
    op.create_index('ix_portfolio_accounts_user_account', 'portfolio_accounts', ['user_id', 'account_id'], schema=SCHEMA)

    # Portfolio Snapshots
    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('account_id', sa.BigInteger(), nullable=False),
        sa.Column('snapshot_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('total_amount_portfolio', sa.Numeric(20, 4), nullable=False),
        sa.Column('total_amount_shares', sa.Numeric(20, 4), nullable=True),
        sa.Column('total_amount_bonds', sa.Numeric(20, 4), nullable=True),
        sa.Column('total_amount_etf', sa.Numeric(20, 4), nullable=True),
        sa.Column('total_amount_currencies', sa.Numeric(20, 4), nullable=True),
        sa.Column('total_amount_futures', sa.Numeric(20, 4), nullable=True),
        sa.Column('total_amount_options', sa.Numeric(20, 4), nullable=True),
        sa.Column('total_amount_sp', sa.Numeric(20, 4), nullable=True),
        sa.Column('expected_yield', sa.Numeric(10, 4), nullable=True),
        sa.Column('daily_yield', sa.Numeric(20, 4), nullable=True),
        sa.Column('daily_yield_relative', sa.Numeric(10, 4), nullable=True),
        sa.Column('currency', sa.String(10), nullable=False, server_default='RUB'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['account_id'], [f'{SCHEMA}.portfolio_accounts.id'], ondelete='CASCADE'),
        schema=SCHEMA,
    )
    op.create_index('ix_portfolio_snapshots_account_date', 'portfolio_snapshots', ['account_id', 'snapshot_date'], schema=SCHEMA)

    # Portfolio Positions
    op.create_table(
        'portfolio_positions',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('snapshot_id', sa.BigInteger(), nullable=False),
        sa.Column('figi', sa.String(20), nullable=True),
        sa.Column('instrument_uid', sa.String(50), nullable=True),
        sa.Column('position_uid', sa.String(50), nullable=True),
        sa.Column('ticker', sa.String(50), nullable=True),
        sa.Column('class_code', sa.String(20), nullable=True),
        sa.Column('instrument_type', sa.String(30), nullable=False),
        sa.Column('quantity', sa.Numeric(20, 4), nullable=False),
        sa.Column('quantity_lots', sa.Numeric(20, 4), nullable=True),
        sa.Column('average_position_price', sa.Numeric(20, 4), nullable=True),
        sa.Column('average_position_price_fifo', sa.Numeric(20, 4), nullable=True),
        sa.Column('current_price', sa.Numeric(20, 4), nullable=True),
        sa.Column('average_position_price_pt', sa.Numeric(20, 4), nullable=True),
        sa.Column('expected_yield', sa.Numeric(10, 4), nullable=True),
        sa.Column('expected_yield_fifo', sa.Numeric(10, 4), nullable=True),
        sa.Column('daily_yield', sa.Numeric(20, 4), nullable=True),
        sa.Column('var_margin', sa.Numeric(20, 4), nullable=True),
        sa.Column('current_nkd', sa.Numeric(20, 4), nullable=True),
        sa.Column('blocked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('blocked_lots', sa.Numeric(20, 4), nullable=True),
        sa.Column('extra_data', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['snapshot_id'], [f'{SCHEMA}.portfolio_snapshots.id'], ondelete='CASCADE'),
        schema=SCHEMA,
    )
    op.create_index('ix_portfolio_positions_snapshot', 'portfolio_positions', ['snapshot_id'], schema=SCHEMA)
    op.create_index('ix_portfolio_positions_figi', 'portfolio_positions', ['figi'], schema=SCHEMA)
    op.create_index('ix_portfolio_positions_ticker', 'portfolio_positions', ['ticker'], schema=SCHEMA)

    # Portfolio Operations
    op.create_table(
        'portfolio_operations',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('account_id', sa.BigInteger(), nullable=False),
        sa.Column('operation_id', sa.String(50), nullable=False, unique=True),
        sa.Column('parent_operation_id', sa.String(50), nullable=True),
        sa.Column('figi', sa.String(20), nullable=True),
        sa.Column('instrument_type', sa.String(30), nullable=True),
        sa.Column('instrument_uid', sa.String(50), nullable=True),
        sa.Column('position_uid', sa.String(50), nullable=True),
        sa.Column('operation_type', sa.String(50), nullable=False),
        sa.Column('operation_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('quantity', sa.Numeric(20, 4), nullable=False),
        sa.Column('quantity_rest', sa.Numeric(20, 4), nullable=True),
        sa.Column('price', sa.Numeric(20, 4), nullable=False),
        sa.Column('price_currency', sa.String(10), nullable=False),
        sa.Column('payment', sa.Numeric(20, 4), nullable=False),
        sa.Column('payment_currency', sa.String(10), nullable=False),
        sa.Column('commission', sa.Numeric(20, 4), nullable=True),
        sa.Column('commission_currency', sa.String(10), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('trades', sa.JSON, nullable=True),
        sa.Column('extra_data', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['account_id'], [f'{SCHEMA}.portfolio_accounts.id'], ondelete='CASCADE'),
        schema=SCHEMA,
    )
    op.create_index('ix_portfolio_operations_account_date', 'portfolio_operations', ['account_id', 'operation_date'], schema=SCHEMA)
    op.create_index('ix_portfolio_operations_operation_id', 'portfolio_operations', ['operation_id'], schema=SCHEMA)
    op.create_index('ix_portfolio_operations_figi', 'portfolio_operations', ['figi'], schema=SCHEMA)

    # Portfolio Orders
    op.create_table(
        'portfolio_orders',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('account_id', sa.BigInteger(), nullable=False),
        sa.Column('order_id', sa.String(50), nullable=False, unique=True),
        sa.Column('figi', sa.String(20), nullable=True),
        sa.Column('instrument_uid', sa.String(50), nullable=True),
        sa.Column('order_type', sa.String(30), nullable=False),
        sa.Column('order_direction', sa.String(20), nullable=False),
        sa.Column('order_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lots_requested', sa.Numeric(20, 4), nullable=False),
        sa.Column('lots_executed', sa.Numeric(20, 4), nullable=True),
        sa.Column('price', sa.Numeric(20, 4), nullable=True),
        sa.Column('execution_price', sa.Numeric(20, 4), nullable=True),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('commission', sa.Numeric(20, 4), nullable=True),
        sa.Column('commission_currency', sa.String(10), nullable=True),
        sa.Column('extra_data', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['account_id'], [f'{SCHEMA}.portfolio_accounts.id'], ondelete='CASCADE'),
        schema=SCHEMA,
    )
    op.create_index('ix_portfolio_orders_account_date', 'portfolio_orders', ['account_id', 'order_date'], schema=SCHEMA)
    op.create_index('ix_portfolio_orders_order_id', 'portfolio_orders', ['order_id'], schema=SCHEMA)

    # Instrument Cache
    op.create_table(
        'instrument_cache',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('figi', sa.String(20), nullable=False, unique=True),
        sa.Column('ticker', sa.String(50), nullable=True),
        sa.Column('isin', sa.String(20), nullable=True),
        sa.Column('instrument_uid', sa.String(50), nullable=True),
        sa.Column('position_uid', sa.String(50), nullable=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('instrument_type', sa.String(30), nullable=False),
        sa.Column('currency', sa.String(10), nullable=True),
        sa.Column('lot', sa.Integer(), nullable=True),
        sa.Column('nominal', sa.Numeric(20, 4), nullable=True),
        sa.Column('nominal_currency', sa.String(10), nullable=True),
        sa.Column('maturity_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sector', sa.String(100), nullable=True),
        sa.Column('extra_data', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index('ix_instrument_cache_figi', 'instrument_cache', ['figi'], schema=SCHEMA)
    op.create_index('ix_instrument_cache_ticker', 'instrument_cache', ['ticker'], schema=SCHEMA)


def downgrade():
    op.drop_table('instrument_cache', schema=SCHEMA)
    op.drop_table('portfolio_orders', schema=SCHEMA)
    op.drop_table('portfolio_operations', schema=SCHEMA)
    op.drop_table('portfolio_positions', schema=SCHEMA)
    op.drop_table('portfolio_snapshots', schema=SCHEMA)
    op.drop_table('portfolio_accounts', schema=SCHEMA)