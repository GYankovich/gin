"""Add order_type to robots_v2_orders (MARKET / LIMIT)."""

from alembic import op
import sqlalchemy as sa

revision = "0061_robots_v2_orders_type"
down_revision = "0060_robots_v2_signals_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "robots_v2_orders",
        sa.Column(
            "order_type",
            sa.String(length=16),
            nullable=False,
            server_default="MARKET",
        ),
    )


def downgrade() -> None:
    op.drop_column("robots_v2_orders", "order_type")
