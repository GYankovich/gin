"""Worker leases: one active process per background job lane.

Revision ID: 0051_background_worker_leases
Revises: 0050_dict_portfolio_orders
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0051_background_worker_leases"
down_revision = "0050_dict_portfolio_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_worker_leases",
        sa.Column("lane", sa.String(32), primary_key=True),
        sa.Column("worker_id", UUID(as_uuid=True), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="running"
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        )
    )
    op.create_index(
        "ix_bg_worker_leases_status_hb",
        "background_worker_leases",
        ["status", "heartbeat_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_bg_worker_leases_status_hb", table_name="background_worker_leases")
    op.drop_table("background_worker_leases")
