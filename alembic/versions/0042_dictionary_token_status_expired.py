"""Add TOKEN.STATUS=3 (expired) dictionary row.

Revision ID: 0042_token_status_expired
Revises: 0041_robot_session_logs
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0042_token_status_expired"
down_revision = "0041_robot_session_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            INSERT INTO {SCHEMA}.dictionary
                (table_name, column_name, num_value, string_value, name, description, hide_from_ui)
            SELECT 'TOKEN', 'STATUS', 3, 'expired', 'Истекший', 'Токен истек', 0
            WHERE NOT EXISTS (
                SELECT 1 FROM {SCHEMA}.dictionary
                WHERE table_name = 'TOKEN'
                  AND column_name = 'STATUS'
                  AND num_value = 3
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
              AND column_name = 'STATUS'
              AND num_value = 3
            """
        )
    )
