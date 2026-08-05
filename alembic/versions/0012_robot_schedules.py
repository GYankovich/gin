"""create robot_schedules table

Revision ID: 0012_robot_schedules
Revises: 0011_drop_old_tables
Create Date: 2026-03-24 10:00:00.000000

"""
#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0012RobotSchedules [1]
#/// Исходный модуль `alembic/versions/0012_robot_schedules.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0012_robot_schedules'
down_revision = '0011_drop_old_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Создаем таблицу расписаний роботов
    op.create_table(
        'robot_schedules',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('robot_id', sa.BigInteger(), nullable=False),

        # Тип расписания: 1=interval, 2=time_range
        sa.Column('schedule_type', sa.Integer(), nullable=False),

        # Для interval-режима (в секундах)
        sa.Column('interval_seconds', sa.Integer(), nullable=True),

        # Для time_range-режима (работа в определенные часы)
        sa.Column('start_time', sa.Time(timezone=True), nullable=True),
        sa.Column('end_time', sa.Time(timezone=True), nullable=True),

        # Дни недели (битовая маска: 1=пн, 2=вт, 4=ср, 8=чт, 16=пт, 32=сб, 64=вс)
        sa.Column('weekdays', sa.Integer(), nullable=True),

        # Общие поля
        sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('usercre', sa.BigInteger(), nullable=True),
        sa.Column('date_creation', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('usermod', sa.BigInteger(), nullable=True),
        sa.Column('date_modification', sa.DateTime(timezone=True), nullable=True),

        # Foreign keys
        sa.ForeignKeyConstraint(['robot_id'], [f'robots.id'], ondelete='CASCADE')
    )

    # Индексы
    op.create_index('ix_robot_schedules_robot_id', 'robot_schedules', ['robot_id'])
    op.create_index('ix_robot_schedules_active', 'robot_schedules', ['is_active'])
    op.create_index('ix_robot_schedules_type', 'robot_schedules', ['schedule_type'])

    print("✅ Table 'robot_schedules' created successfully.")


def downgrade():
    op.drop_table('robot_schedules')
    print("✅ Table 'robot_schedules' dropped.")