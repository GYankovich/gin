"""add robot_logs table

Revision ID: 0005_add_robot_logs
Revises: 0004_add_refresh_interval  # Замените на ID вашей последней миграции
Create Date: 2026-03-04 15:00:00.000000

"""
#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0005AddRobotLogs [1]
#/// Исходный модуль `alembic/versions/0005_add_robot_logs.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0005_add_robot_logs'
down_revision = '0004_add_refresh_interval'  # Укажите правильный ID предыдущей миграции
branch_labels = None
depends_on = None


def upgrade():
    # Создаем таблицу robot_logs
    op.create_table(
        'robot_logs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('robot_name', sa.String(100), nullable=False),
        sa.Column('robot_version', sa.String(20), nullable=True),
        sa.Column('token_id', sa.BigInteger(), nullable=True),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('endpoint', sa.String(500), nullable=False),
        sa.Column('request_data', sa.JSON, nullable=True),
        sa.Column('response_status', sa.Integer(), nullable=True),
        sa.Column('response_data', sa.JSON, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('success', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        # Внешние ключи
        sa.ForeignKeyConstraint(['token_id'], [f'api_tokens.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], [f'user.id'], ondelete='SET NULL')
    )

    # Создаем индексы для быстрого поиска
    op.create_index('ix_robot_logs_robot_name', 'robot_logs', ['robot_name'])
    op.create_index('ix_robot_logs_token_id', 'robot_logs', ['token_id'])
    op.create_index('ix_robot_logs_user_id', 'robot_logs', ['user_id'])
    op.create_index('ix_robot_logs_created_at', 'robot_logs', ['created_at'])
    op.create_index('ix_robot_logs_success', 'robot_logs', ['success'])
    op.create_index('ix_robot_logs_started_at', 'robot_logs', ['started_at'])


def downgrade():
    # Удаляем индексы
    op.drop_index('ix_robot_logs_robot_name', table_name='robot_logs')
    op.drop_index('ix_robot_logs_token_id', table_name='robot_logs')
    op.drop_index('ix_robot_logs_user_id', table_name='robot_logs')
    op.drop_index('ix_robot_logs_created_at', table_name='robot_logs')
    op.drop_index('ix_robot_logs_success', table_name='robot_logs')
    op.drop_index('ix_robot_logs_started_at', table_name='robot_logs')

    # Удаляем таблицу
    op.drop_table('robot_logs')