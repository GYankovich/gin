"""migrate robot schedules from api_tokens refresh_interval

Revision ID: 0014_migrate_schedules
Revises: 0013_robot_strategies
Create Date: 2026-03-24 10:10:00.000000

"""
#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0014MigrateSchedules [1]
#/// Исходный модуль `alembic/versions/0014_migrate_schedules.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0014_migrate_schedules'
down_revision = '0013_robot_strategies'
branch_labels = None
depends_on = None


def upgrade():
    # Проверяем существование колонки refresh_interval_minutes в api_tokens
    # и переносим данные в robot_schedules для существующих роботов
    op.execute(f"""
        INSERT INTO {SCHEMA}.  (robot_id, schedule_type, interval_seconds, is_active, description)
        SELECT 
            r.id,
            1 as schedule_type,  -- interval type
            a.refresh_interval_minutes * 60 as interval_seconds,
            CASE WHEN r.status = 0 THEN 1 ELSE 0 END as is_active,  -- если статус робота не заблокирован
            'Migrated from api_tokens refresh_interval' as description
        FROM {SCHEMA}.robots r
        INNER JOIN {SCHEMA}.api_tokens a ON r.token_id = a.id
        WHERE a.refresh_interval_minutes IS NOT NULL
        ON CONFLICT DO NOTHING
    """)

    print("✅ Robot schedules migrated from api_tokens successfully.")


def downgrade():
    # Удаляем только мигрированные записи с description как у миграции
    op.execute(f"""
        DELETE FROM {SCHEMA}.robot_schedules 
        WHERE description = 'Migrated from api_tokens refresh_interval'
    """)

    print("⚠️ Migrated robot schedules removed.")