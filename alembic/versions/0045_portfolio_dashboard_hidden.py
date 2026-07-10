"""Add dashboard_hidden flag to portfolio_accounts.

Revision ID: 0045_portfolio_dashboard_hidden
Revises: 0044_dict_portfolio_instr_type
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0045_portfolio_dashboard_hidden"
down_revision = "0044_dict_portfolio_instr_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolio_accounts",
        sa.Column("dashboard_hidden", sa.Integer(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("portfolio_accounts", "dashboard_hidden", schema=SCHEMA)
