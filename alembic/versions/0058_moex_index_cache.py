"""MOEX index composition cache.

Revision ID: 0058_moex_index_cache
Revises: 0057_robots_v2
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0058_moex_index_cache"
down_revision = "0057_robots_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "moex_index_cache",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("index_code", sa.String(length=32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("tickers", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("index_code", "as_of_date", name="uq_moex_index_cache_code_date"),
    )
    op.create_index("ix_moex_index_cache_code_date", "moex_index_cache", ["index_code", "as_of_date"])


def downgrade() -> None:
    op.drop_index("ix_moex_index_cache_code_date", table_name="moex_index_cache")
    op.drop_table("moex_index_cache")
