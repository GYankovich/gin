#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0017AddExecutionLogId [1]
#/// Исходный модуль `alembic/versions/0017_add_execution_log_id.py` — автоматическая разметка для Obsidian Source Scanner.

# alembic/versions/0017_add_execution_log_id_to_robot_logs.py
"""add execution_log_id to robot_logs

Revision ID: 0017_add_execution_log_id
Revises: 0016_robot_logs
Create Date: 2026-03-24 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0017_add_execution_log_id'
down_revision = '0016_robot_logs'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем поле execution_log_id
    op.add_column(
        'robot_logs',
        sa.Column('execution_log_id', sa.BigInteger(), nullable=True)
    )

    # Добавляем внешний ключ
    op.create_foreign_key(
        'fk_robot_logs_execution_log',
        'robot_logs',
        'robot_execution_logs',
        ['execution_log_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Добавляем индекс
    op.create_index(
        'ix_robot_logs_execution_log_id',
        'robot_logs',
        ['execution_log_id']
    )


def downgrade():
    # Удаляем индекс
    op.drop_index('ix_robot_logs_execution_log_id', table_name='robot_logs')

    # Удаляем внешний ключ
    op.drop_constraint('fk_robot_logs_execution_log', 'robot_logs', type_='foreignkey')

    # Удаляем поле
    op.drop_column('robot_logs', 'execution_log_id')