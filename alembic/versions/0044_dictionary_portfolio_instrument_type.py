"""Add PORTFOLIO_POSITIONS.INSTRUMENT_TYPE dictionary rows.

Revision ID: 0044_dict_portfolio_instr_type
Revises: 0043_api_tokens_status
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0044_dict_portfolio_instr_type"
down_revision = "0043_api_tokens_status"
branch_labels = None
depends_on = None

_ROWS = [
    (1, "share", "Акции РФ", "Акции российского рынка"),
    (2, "bond", "Облигации", "Облигации"),
    (3, "etf", "ETF / Фонды", "Биржевые фонды и ETF"),
    (4, "currency", "Деньги (кеш)", "Денежные средства и валюта"),
    (5, "crypto_perpetual", "Криптовалюты", "Крипто-перпетуалы и крипто-позиции"),
    (6, "future", "Фьючерсы", "Фьючерсные контракты"),
    (7, "option", "Опционы", "Опционные контракты"),
]


def upgrade() -> None:
    for num_value, string_value, name, description in _ROWS:
        op.execute(
            sa.text(
                f"""
                INSERT INTO dictionary
                    (table_name, column_name, num_value, string_value, name, description, hide_from_ui)
                SELECT
                    'PORTFOLIO_POSITIONS',
                    'INSTRUMENT_TYPE',
                    :num_value,
                    :string_value,
                    :name,
                    :description,
                    0
                WHERE NOT EXISTS (
                    SELECT 1 FROM dictionary
                    WHERE table_name = 'PORTFOLIO_POSITIONS'
                      AND column_name = 'INSTRUMENT_TYPE'
                      AND string_value = :string_value
                )
                """
            ).bindparams(
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
            WHERE table_name = 'PORTFOLIO_POSITIONS'
              AND column_name = 'INSTRUMENT_TYPE'
            """
        )
    )
