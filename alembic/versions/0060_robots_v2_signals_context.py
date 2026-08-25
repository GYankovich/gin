"""Add entry_price and delta_pct to robots_v2_signals.

Revision ID: 0060_robots_v2_signals_context
Revises: 0059_robots_v2_audit
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0060_robots_v2_signals_context"
down_revision = "0059_robots_v2_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "robots_v2_signals",
        sa.Column("entry_price", sa.Numeric(20, 6), nullable=True),
    )
    op.add_column(
        "robots_v2_signals",
        sa.Column("delta_pct", sa.Numeric(12, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("robots_v2_signals", "delta_pct")
    op.drop_column("robots_v2_signals", "entry_price")
