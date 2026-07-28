"""Add ByBit token type to dictionary.

Revision ID: 0038_dictionary_token_type_bybit
Revises: 0037_background_jobs
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0038_dictionary_token_type_bybit"
down_revision = "0037_background_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            INSERT INTO {SCHEMA}.dictionary
                (table_name, column_name, num_value, string_value, name, description, hide_from_ui)
            SELECT 'TOKEN', 'TYPE', 2, 'bybit', 'ByBit', 'API Key и Secret для ByBit', 0
            WHERE NOT EXISTS (
                SELECT 1 FROM {SCHEMA}.dictionary
                WHERE table_name = 'TOKEN'
                  AND column_name = 'TYPE'
                  AND num_value = 2
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"""
            DELETE FROM {SCHEMA}.dictionary
            WHERE table_name = 'TOKEN'
              AND column_name = 'TYPE'
              AND num_value = 2
            """
        )
    )
