"""create trading robots tables

Revision ID: 0006_create_trading_robots
Revises: 0005_add_robot_logs
Create Date: 2026-03-12 16:00:00.000000

"""
#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0006CreateTradingRobots [1]
#/// Исходный модуль `alembic/versions/0006_create_trading_robots.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0006_create_trading_robots'
down_revision = '0005_add_robot_logs'
branch_labels = None
depends_on = None


def upgrade():
    # Создаём таблицу trading_robots
    op.create_table(
        'trading_robots',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('token_id', sa.BigInteger(), nullable=False),
        sa.Column('account_id', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('strategy_name', sa.String(50), nullable=False),
        sa.Column('strategy_params', sa.JSON(), nullable=True),
        sa.Column('max_position_size_percent', sa.Float(), nullable=False, server_default='10.0'),
        sa.Column('stop_loss_percent', sa.Float(), nullable=True),
        sa.Column('take_profit_percent', sa.Float(), nullable=True),
        sa.Column('daily_loss_limit', sa.Float(), nullable=True),
        sa.Column('max_trades_per_day', sa.Integer(), nullable=True),
        sa.Column('schedule_cron', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('total_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_profit', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], [f'{SCHEMA}.user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['token_id'], [f'{SCHEMA}.api_tokens.id'], ondelete='CASCADE'),
        schema=SCHEMA,
    )

    op.create_index('ix_trading_robots_user_id', 'trading_robots', ['user_id'], schema=SCHEMA)
    op.create_index('ix_trading_robots_token_id', 'trading_robots', ['token_id'], schema=SCHEMA)
    op.create_index('ix_trading_robots_is_active', 'trading_robots', ['is_active'], schema=SCHEMA)

    # Создаём таблицу robot_trades
    op.create_table(
        'robot_trades',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('robot_id', sa.BigInteger(), nullable=False),
        sa.Column('figi', sa.String(20), nullable=False),
        sa.Column('direction', sa.String(10), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('total_value', sa.Float(), nullable=False),
        sa.Column('commission', sa.Float(), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('profit', sa.Float(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['robot_id'], [f'{SCHEMA}.trading_robots.id'], ondelete='CASCADE'),
        schema=SCHEMA,
    )

    op.create_index('ix_robot_trades_robot_id', 'robot_trades', ['robot_id'], schema=SCHEMA)
    op.create_index('ix_robot_trades_opened_at', 'robot_trades', ['opened_at'], schema=SCHEMA)
    op.create_index('ix_robot_trades_figi', 'robot_trades', ['figi'], schema=SCHEMA)


def downgrade():
    op.drop_table('robot_trades', schema=SCHEMA)
    op.drop_table('trading_robots', schema=SCHEMA)