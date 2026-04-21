"""Normalize robots config to grain_seed-only.

Revision ID: 0024_grain_seed_only_robots
Revises: 0023_widen_po_status
Create Date: 2026-04-15
"""

from alembic import op
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0024_grain_seed_only_robots"
down_revision = "0023_widen_po_status"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Все роботы переводим на trading-type, чтобы UI/API работали единообразно.
    op.execute(f"UPDATE {SCHEMA}.robots SET type = 2 WHERE type <> 2")

    # 2) Нормализуем config в grain_seed-формат.
    op.execute(
        f"""
        UPDATE {SCHEMA}.robots
        SET config = jsonb_set(
            jsonb_set(
                jsonb_set(
                    jsonb_set(
                        jsonb_set(
                            COALESCE(config::jsonb, '{{}}'::jsonb),
                            '{{strategy}}', '\"grain_seed\"'::jsonb, true
                        ),
                        '{{broker_type}}', '\"tinvest\"'::jsonb, true
                    ),
                    '{{allowed_figis}}',
                    COALESCE(config::jsonb->'allowed_figis', '[]'::jsonb),
                    true
                ),
                '{{strategy_params}}',
                COALESCE(config::jsonb->'strategy_params', '{{}}'::jsonb),
                true
            ),
            '{{risk}}',
            COALESCE(config::jsonb->'risk', '{{}}'::jsonb),
            true
        )
        """
    )

    # 3) Обновляем интервал цикла для роботов без значения.
    op.execute(
        f"""
        UPDATE {SCHEMA}.robots
        SET config = jsonb_set(config::jsonb, '{{update_interval_seconds}}', '10'::jsonb, true)
        WHERE COALESCE((config::jsonb->>'update_interval_seconds'), '') = ''
        """
    )

    # 4) Добавляем ключ force_market_flatten по умолчанию в strategy_params.
    op.execute(
        f"""
        UPDATE {SCHEMA}.robots
        SET config = jsonb_set(
            config::jsonb,
            '{{strategy_params,force_market_flatten}}',
            'true'::jsonb,
            true
        )
        WHERE (config::jsonb->'strategy_params'->>'force_market_flatten') IS NULL
        """
    )

    # Тип стратегии
    op.execute(
        f"""
        INSERT INTO {SCHEMA}.dictionary 
            (table_name, column_name, num_value, name, description, hide_from_ui)
        VALUES 
            ('ROBOT_STRATEGIES', 'TYPE', 1, 'По зернышку, по семечку', 'Медленно, но аккуратно зарабатываем', 0)
        """
    )



def downgrade():
    # Откат данных не выполняем, оставляем текущее значение config как безопасное состояние.
    pass

