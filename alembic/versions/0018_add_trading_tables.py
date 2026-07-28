"""add robot_trades and robot_signals tables

Revision ID: 0018_add_trading_tables
Revises: 0017_add_execution_log_id
Create Date: 2024-03-25 22:30:00.000000

"""
#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0018AddTradingTables [1]
#/// Исходный модуль `alembic/versions/0018_add_trading_tables.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0018_add_trading_tables'
down_revision = '0017_add_execution_log_id'
branch_labels = None
depends_on = None


def upgrade():
    # Создаем таблицу robot_trades
    op.create_table(
        'robot_trades',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('robot_id', sa.BigInteger(), nullable=False),

        # Данные сделки
        sa.Column('figi', sa.String(20), nullable=False),
        sa.Column('ticker', sa.String(50), nullable=True),
        sa.Column('instrument_type', sa.String(30), nullable=True),

        # Направление
        sa.Column('side', sa.String(10), nullable=False),  # buy, sell

        # Количество и цена
        sa.Column('quantity', sa.Numeric(20, 4), nullable=False),
        sa.Column('price', sa.Numeric(20, 4), nullable=False),
        sa.Column('total_amount', sa.Numeric(20, 4), nullable=False),

        # Комиссия
        sa.Column('commission', sa.Numeric(20, 4), nullable=True),
        sa.Column('commission_currency', sa.String(10), nullable=True),

        # ID ордера в T-Invest
        sa.Column('order_id', sa.String(50), nullable=True, unique=True),

        # Цены для трейлинг-стопа
        sa.Column('entry_price', sa.Numeric(20, 4), nullable=True),
        sa.Column('exit_price', sa.Numeric(20, 4), nullable=True),
        sa.Column('max_price_during_hold', sa.Numeric(20, 4), nullable=True),
        sa.Column('min_price_during_hold', sa.Numeric(20, 4), nullable=True),

        # Исполнение
        sa.Column('filled_quantity', sa.Numeric(20, 4), nullable=True),
        sa.Column('avg_fill_price', sa.Numeric(20, 4), nullable=True),

        # Результат сделки
        sa.Column('profit', sa.Numeric(20, 4), nullable=True),
        sa.Column('profit_percent', sa.Numeric(10, 4), nullable=True),

        # Статус
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),

        # Временные метки
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),

        # Аудит
        sa.Column('usercre', sa.BigInteger(), nullable=True),
        sa.Column('date_creation', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        # Внешние ключи
        sa.ForeignKeyConstraint(['robot_id'], [f'{SCHEMA}.robots.id'], ondelete='CASCADE'),

        schema=SCHEMA
    )

    # Индексы для robot_trades
    op.create_index('ix_robot_trades_robot_id', 'robot_trades', ['robot_id'], schema=SCHEMA)
    op.create_index('ix_robot_trades_figi', 'robot_trades', ['figi'], schema=SCHEMA)
    op.create_index('ix_robot_trades_status', 'robot_trades', ['status'], schema=SCHEMA)
    op.create_index('ix_robot_trades_created_at', 'robot_trades', ['created_at'], schema=SCHEMA)

    # Создаем таблицу robot_signals
    op.create_table(
        'robot_signals',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('robot_id', sa.BigInteger(), nullable=False),

        # Инструмент
        sa.Column('figi', sa.String(20), nullable=False),
        sa.Column('ticker', sa.String(50), nullable=True),

        # Сигнал
        sa.Column('signal_type', sa.String(30), nullable=False),  # buy, sell, hold
        sa.Column('signal_strength', sa.Integer(), nullable=True),  # 0-100

        # Данные на момент сигнала
        sa.Column('price_at_signal', sa.Numeric(20, 4), nullable=True),
        sa.Column('indicators', sa.JSON(), nullable=True),

        # Исполнение
        sa.Column('was_executed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('executed_trade_id', sa.BigInteger(), nullable=True),

        # Временные метки
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        # Внешние ключи
        sa.ForeignKeyConstraint(['robot_id'], [f'{SCHEMA}.robots.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['executed_trade_id'], [f'{SCHEMA}.robot_trades.id'], ondelete='SET NULL'),

        schema=SCHEMA
    )

    # Индексы для robot_signals
    op.create_index('ix_robot_signals_robot_id', 'robot_signals', ['robot_id'], schema=SCHEMA)
    op.create_index('ix_robot_signals_figi', 'robot_signals', ['figi'], schema=SCHEMA)
    op.create_index('ix_robot_signals_type', 'robot_signals', ['signal_type'], schema=SCHEMA)
    op.create_index('ix_robot_signals_executed', 'robot_signals', ['was_executed'], schema=SCHEMA)
    op.create_index('ix_robot_signals_created_at', 'robot_signals', ['created_at'], schema=SCHEMA)

    print("✅ Tables robot_trades and robot_signals created successfully.")


def downgrade():
    op.drop_table('robot_signals', schema=SCHEMA)
    op.drop_table('robot_trades', schema=SCHEMA)
    print("✅ Tables robot_trades and robot_signals dropped.")