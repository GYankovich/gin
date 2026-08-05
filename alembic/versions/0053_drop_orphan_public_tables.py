"""drop leftover non-migrated public tables

Revision ID: 0053_drop_orphan_public_tables
Revises: 0052_portfolio_orders_reason
Create Date: 2026-08-03

Tables present in the live DB but never created by Alembic / unused by ORM:
- users (legacy; app uses \"user\")
- tinvest_settings (removed from models)
- portfolio_snapshots_backup (manual backup leftover)
"""
from alembic import op

revision = "0053_drop_orphan_public_tables"
down_revision = "0052_portfolio_orders_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS portfolio_snapshots_backup CASCADE")
    op.execute("DROP TABLE IF EXISTS tinvest_settings CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")


def downgrade() -> None:
    # Intentionally empty: these tables were never part of the migration chain.
    pass
