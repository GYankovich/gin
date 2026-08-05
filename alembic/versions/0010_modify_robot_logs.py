"""modify robot_logs to link with robots table

Revision ID: 0010_modify_robot_logs
Revises: 0009_create_robot_configs_table
Create Date: 2026-03-17 01:30:00.000000

"""
#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0010ModifyRobotLogs [1]
#/// Исходный модуль `alembic/versions/0010_modify_robot_logs.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0010_modify_robot_logs'
down_revision = '0009_create_robot_configs_table'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем колонку robot_id в существующую таблицу robot_logs
    op.add_column(
        'robot_logs',
        sa.Column('robot_id', sa.BigInteger(), nullable=True)
    )

    # Добавляем внешний ключ
    op.create_foreign_key(
        'fk_robot_logs_robot_id',
        'robot_logs',
        'robots',
        ['robot_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Создаём индекс для новой колонки
    op.create_index('ix_robot_logs_robot_id', 'robot_logs', ['robot_id'])


def downgrade():
    # Удаляем внешний ключ
    op.drop_constraint('fk_robot_logs_robot_id', 'robot_logs', type_='foreignkey')

    # Удаляем индекс
    op.drop_index('ix_robot_logs_robot_id', table_name='robot_logs')

    # Удаляем колонку
    op.drop_column('robot_logs', 'robot_id')