"""Rename api_tokens.updated_at → modification_date.

Revision ID: 0090_api_tokens_mod
Revises: 0089_token_secret
"""

from alembic import op

revision = "0090_api_tokens_mod"
down_revision = "0089_token_secret"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE api_tokens
            RENAME COLUMN updated_at TO modification_date
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE api_tokens
            RENAME COLUMN modification_date TO updated_at
        """
    )
