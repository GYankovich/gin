"""add validation fields to robot_configs

Revision ID: 0015_robot_config_val
Revises: 0014_migrate_schedules
Create Date: 2026-03-24 10:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from app.core.config import settings
from sqlalchemy.dialects.postgresql import JSON

SCHEMA = settings.DB_SCHEMA

revision = '0015_robot_config_val'
down_revision = '0014_migrate_schedules'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем поле для JSON схемы валидации в robot_configs
    op.add_column(
        'robot_configs',
        sa.Column('validation_schema', JSON(), nullable=True),
        schema=SCHEMA
    )

    # Добавляем поле для порядка отображения
    op.add_column(
        'robot_configs',
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        schema=SCHEMA
    )

    # Добавляем поле для группировки конфигураций
    op.add_column(
        'robot_configs',
        sa.Column('config_group', sa.String(length=50), nullable=True),
        schema=SCHEMA
    )

    print("✅ Added validation fields to robot_configs.")


def downgrade():
    op.drop_column('robot_configs', 'validation_schema', schema=SCHEMA)
    op.drop_column('robot_configs', 'display_order', schema=SCHEMA)
    op.drop_column('robot_configs', 'config_group', schema=SCHEMA)
    print("⚠️ Validation fields removed from robot_configs.")