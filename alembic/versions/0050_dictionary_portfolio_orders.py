"""Add PORTFOLIO_ORDERS dictionary rows (direction, status, source).

Revision ID: 0050_dict_portfolio_orders
Revises: 0049_portfolio_orders_widen
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0050_dict_portfolio_orders"
down_revision = "0049_portfolio_orders_widen"
branch_labels = None
depends_on = None

# (column_name, num_value, string_value, name, description)
_ROWS = [
    ("ORDER_DIRECTION", 1, "buy", "Покупка", "Лонг / buy"),
    ("ORDER_DIRECTION", 2, "sell", "Продажа", "Шорт / sell"),
    ("STATUS", 1, "pending", "В работе", "Новая / активная заявка"),
    ("STATUS", 2, "partial", "Частично", "Частичное исполнение"),
    ("STATUS", 3, "filled", "Исполнена", "Полностью исполнена"),
    ("STATUS", 4, "cancelled", "Отменена", "Отмена"),
    ("STATUS", 5, "rejected", "Отклонена", "Отклонена брокером / ошибка"),
    ("SOURCE", 1, "robot", "Робот", "Заявка торгового робота"),
    ("SOURCE", 2, "manual", "Вручную", "Ручная заявка из Live"),
    ("SOURCE", 3, "external", "Прочее", "Внешняя / импортированная заявка"),
]


def upgrade() -> None:
    for column_name, num_value, string_value, name, description in _ROWS:
        op.execute(
            sa.text(
                f"""
                INSERT INTO dictionary
                    (table_name, column_name, num_value, string_value, name, description, hide_from_ui)
                SELECT
                    'PORTFOLIO_ORDERS',
                    :column_name,
                    :num_value,
                    :string_value,
                    :name,
                    :description,
                    0
                WHERE NOT EXISTS (
                    SELECT 1 FROM dictionary
                    WHERE table_name = 'PORTFOLIO_ORDERS'
                      AND column_name = :column_name
                      AND string_value = :string_value
                )
                """
            ).bindparams(
                column_name=column_name,
                num_value=num_value,
                string_value=string_value,
                name=name,
                description=description
            )
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"""
            DELETE FROM dictionary
            WHERE table_name = 'PORTFOLIO_ORDERS'
              AND column_name IN ('ORDER_DIRECTION', 'STATUS', 'SOURCE')
            """
        )
    )
