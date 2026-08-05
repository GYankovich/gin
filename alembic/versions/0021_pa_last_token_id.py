"""add last_token_id to portfolio_accounts

Revision ID: 0021_pa_last_token_id
Revises: 0020_market_backtests
Create Date: 2026-04-07 12:00:00.000000

"""

#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0021PaLastTokenId [1]
#/// Исходный модуль `alembic/versions/0021_pa_last_token_id.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0021_pa_last_token_id"
down_revision = "0020_market_backtests"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "portfolio_accounts",
        sa.Column("last_token_id", sa.BigInteger(), nullable=True)
    )
    op.create_index(
        "ix_portfolio_accounts_last_token_id",
        "portfolio_accounts",
        ["last_token_id"],
        unique=False
    )


def downgrade():
    op.drop_index("ix_portfolio_accounts_last_token_id", table_name="portfolio_accounts")
    op.drop_column("portfolio_accounts", "last_token_id")
