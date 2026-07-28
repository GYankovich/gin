"""Add portfolio_orders.reason + PORTFOLIO_ORDERS REASON dictionary.

Revision ID: 0052_portfolio_orders_reason
Revises: 0051_background_worker_leases
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0052_portfolio_orders_reason"
down_revision = "0051_background_worker_leases"
branch_labels = None
depends_on = None

# (num_value, string_value, name, description)
_REASON_ROWS = [
    (1, "stop_loss", "Стоп-лосс", "Закрытие по stop-loss"),
    (2, "take_profit", "Тейк-профит", "Закрытие по take-profit"),
    (3, "entry", "Вход", "Открытие позиции по сигналу"),
    (4, "exit_strategy", "Выход (сигнал)", "Закрытие по сигналу стратегии"),
    (5, "exit_sl_tp", "SL/TP", "Закрытие по SL/TP (без уточнения)"),
    (6, "flatten", "Принудительное закрытие", "Force flatten / grain_seed"),
    (7, "manual", "Вручную", "Ручная заявка из Live"),
    (8, "external", "Внешняя", "Импорт с брокера / прочее"),
]


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            ALTER TABLE {SCHEMA}.portfolio_orders
            ADD COLUMN IF NOT EXISTS reason VARCHAR(64) NULL
            """
        )
    )
    for num_value, string_value, name, description in _REASON_ROWS:
        op.execute(
            sa.text(
                f"""
                INSERT INTO {SCHEMA}.dictionary
                    (table_name, column_name, num_value, string_value, name, description, hide_from_ui)
                SELECT
                    'PORTFOLIO_ORDERS',
                    'REASON',
                    :num_value,
                    :string_value,
                    :name,
                    :description,
                    0
                WHERE NOT EXISTS (
                    SELECT 1 FROM {SCHEMA}.dictionary
                    WHERE table_name = 'PORTFOLIO_ORDERS'
                      AND column_name = 'REASON'
                      AND string_value = :string_value
                )
                """
            ).bindparams(
                num_value=num_value,
                string_value=string_value,
                name=name,
                description=description,
            )
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"""
            DELETE FROM {SCHEMA}.dictionary
            WHERE table_name = 'PORTFOLIO_ORDERS'
              AND column_name = 'REASON'
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            ALTER TABLE {SCHEMA}.portfolio_orders
            DROP COLUMN IF EXISTS reason
            """
        )
    )
