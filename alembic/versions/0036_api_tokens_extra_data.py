"""Add extra_data (and account_id) to api_tokens for ByBit/crypto token metadata.

Revision ID: 0036_api_tokens_extra_data
Revises: 0035_bybit_funding_history
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0036_api_tokens_extra_data"
down_revision = "0035_bybit_funding_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            ALTER TABLE {SCHEMA}.api_tokens
                ADD COLUMN IF NOT EXISTS extra_data JSONB;
            ALTER TABLE {SCHEMA}.api_tokens
                ADD COLUMN IF NOT EXISTS account_id VARCHAR(50);
            """
        )
    )


def downgrade() -> None:
    op.drop_column("api_tokens", "account_id", schema=SCHEMA)
    op.drop_column("api_tokens", "extra_data", schema=SCHEMA)
