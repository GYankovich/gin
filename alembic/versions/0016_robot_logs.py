"""add robot_execution_logs table

Revision ID: 0016_robot_logs
Revises: 0015_robot_config_val
Create Date: 2026-03-24 10:20:00.000000

"""
#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0016RobotLogs [1]
#/// Исходный модуль `alembic/versions/0016_robot_logs.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings
from sqlalchemy.dialects.postgresql import JSON

SCHEMA = settings.DB_SCHEMA

revision = '0016_robot_logs'
down_revision = '0015_robot_config_val'
branch_labels = None
depends_on = None


def upgrade():
    # Создаем таблицу логов выполнения роботов
    op.create_table(
        'robot_execution_logs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('robot_id', sa.BigInteger(), nullable=False),
        sa.Column('strategy_id', sa.BigInteger(), nullable=True),

        # Тип действия: 1=start, 2=stop, 3=error, 4=signal, 5=trade
        sa.Column('action_type', sa.Integer(), nullable=False),

        # Статус: 0=success, 1=failed, 2=pending
        sa.Column('status', sa.Integer(), nullable=False),

        # Сообщение и детали
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('details', JSON(), nullable=True),

        # Метрики выполнения (время, затраты и т.д.)
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('error_stack', sa.Text(), nullable=True),

        # Аудит
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        # Foreign keys
        sa.ForeignKeyConstraint(['robot_id'], [f'robots.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['strategy_id'], [f'robot_strategies.id'], ondelete='SET NULL')
    )

    # Индексы для быстрого поиска
    op.create_index('ix_robot_logs_robot_id_1', 'robot_execution_logs', ['robot_id'])
    op.create_index('ix_robot_logs_created_at_1', 'robot_execution_logs', ['created_at'])
    op.create_index('ix_robot_logs_status_1', 'robot_execution_logs', ['status'])
    op.create_index('ix_robot_logs_action_type_1', 'robot_execution_logs', ['action_type'])

    print("✅ Table 'robot_execution_logs' created successfully.")


def downgrade():
    op.drop_table('robot_execution_logs')
    print("✅ Table 'robot_execution_logs' dropped.")