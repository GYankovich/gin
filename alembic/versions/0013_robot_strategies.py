"""create robot_strategies table

Revision ID: 0013_robot_strategies
Revises: 0012_robot_schedules
Create Date: 2026-03-24 10:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from app.core.config import settings
from sqlalchemy.dialects.postgresql import JSON

SCHEMA = settings.DB_SCHEMA

revision = '0013_robot_strategies'
down_revision = '0012_robot_schedules'
branch_labels = None
depends_on = None


def upgrade():
    # Создаем таблицу стратегий роботов
    op.create_table(
        'robot_strategies',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('robot_id', sa.BigInteger(), nullable=False),

        # Тип стратегии (ссылка на dictionary)
        sa.Column('type', sa.Integer(), nullable=False),

        # Параметры стратегии в JSON (гибкая структура)
        sa.Column('parameters', JSON(), nullable=False, server_default='{}'),

        # Валидация параметров (JSON Schema)
        sa.Column('validation_schema', JSON(), nullable=True),

        # Версионирование
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_default', sa.Integer(), nullable=False, server_default='0'),

        # Аудит
        sa.Column('usercre', sa.BigInteger(), nullable=True),
        sa.Column('date_creation', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('usermod', sa.BigInteger(), nullable=True),
        sa.Column('date_modification', sa.DateTime(timezone=True), nullable=True),

        # Foreign keys
        sa.ForeignKeyConstraint(['robot_id'], [f'{SCHEMA}.robots.id'], ondelete='CASCADE'),
        schema=SCHEMA,
    )

    # Индексы
    op.create_index('ix_robot_strategies_robot_id', 'robot_strategies', ['robot_id'], schema=SCHEMA)
    op.create_index('ix_robot_strategies_type', 'robot_strategies', ['strategy_type'], schema=SCHEMA)
    op.create_index('ix_robot_strategies_active', 'robot_strategies', ['is_active'], schema=SCHEMA)

    print("✅ Table 'robot_strategies' created successfully.")


def downgrade():
    op.drop_table('robot_strategies', schema=SCHEMA)
    print("✅ Table 'robot_strategies' dropped.")