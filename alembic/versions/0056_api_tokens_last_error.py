"""Add last_error / last_error_at to api_tokens.

Revision ID: 0056_api_tokens_last_error
Revises: 0055_portfolio_ops_dictionary
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0056_api_tokens_last_error"
down_revision = "0055_portfolio_ops_dictionary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_tokens",
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "api_tokens",
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_tokens", "last_error_at")
    op.drop_column("api_tokens", "last_error")
