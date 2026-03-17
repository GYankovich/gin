"""create robot_configs table

Revision ID: 0009_create_robot_configs_table
Revises: 0008_create_robots_table
Create Date: 2026-03-17 01:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0009_create_robot_configs_table'
down_revision = '0008_create_robots_table'
branch_labels = None
depends_on = None


def upgrade():
    # Создаём таблицу для хранения шаблонов конфигурации по типам роботов
    op.create_table(
        'robot_configs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('robot_type', sa.Integer(), nullable=False),  # ссылка на dictionary
        sa.Column('config_key', sa.String(length=100), nullable=False),
        sa.Column('config_value', sa.JSON(), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_required', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('usercre', sa.BigInteger(), nullable=True),
        sa.Column('date_creation', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('usermod', sa.BigInteger(), nullable=True),
        sa.Column('date_modification', sa.DateTime(timezone=True), nullable=True),

        schema=SCHEMA,
    )

    op.create_index('ix_robot_configs_type', 'robot_configs', ['robot_type'], schema=SCHEMA)
    op.create_index('ix_robot_configs_key', 'robot_configs', ['config_key'], schema=SCHEMA)

    # Добавляем конфигурации для разных типов роботов

    # Для робота обновления портфеля (type = 1)
    op.execute(f"""
        INSERT INTO {SCHEMA}.robot_configs 
            (robot_type, config_key, config_value, description, is_required)
        VALUES 
            (1, 'refresh_interval', '{{"type": "integer", "default": 60, "min": 5, "max": 1440, "label": "Интервал обновления (мин)"}}', 'Частота обновления портфеля', 1),
            (1, 'include_inactive', '{{"type": "boolean", "default": false, "label": "Включать неактивные счета"}}', 'Обновлять ли неактивные счета', 0)
    """)

    # Для торгового робота (type = 2)
    op.execute(f"""
        INSERT INTO {SCHEMA}.robot_configs 
            (robot_type, config_key, config_value, description, is_required)
        VALUES 
            (2, 'strategy_name', '{{"type": "string", "default": "ma_cross", "enum": ["ma_cross"], "label": "Стратегия"}}', 'Торговая стратегия', 1),
            (2, 'strategy_params', '{{"type": "json", "default": {{"fast_period": 10, "slow_period": 30}}, "label": "Параметры стратегии"}}', 'Параметры стратегии', 1),
            (2, 'max_daily_loss', '{{"type": "float", "default": 5, "min": 0, "max": 100, "label": "Макс. дневной убыток %"}}', 'Максимальный дневной убыток в процентах', 0),
            (2, 'max_position_size', '{{"type": "float", "default": 10000, "min": 0, "label": "Макс. размер позиции (руб)"}}', 'Максимальный размер позиции в рублях', 0),
            (2, 'allowed_instruments', '{{"type": "array", "default": [], "label": "Разрешенные инструменты (FIGI)"}}', 'Список FIGI для торговли', 0)
    """)


def downgrade():
    op.drop_table('robot_configs', schema=SCHEMA)