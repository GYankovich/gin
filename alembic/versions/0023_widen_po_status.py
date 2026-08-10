"""Widen portfolio_operations.status for T-Invest operation state enums

Revision ID: 0023_widen_po_status
Revises: 0022_ext_api_logs
Create Date: 2026-04-13

OPERATION_STATE_* values exceed VARCHAR(20) (e.g. OPERATION_STATE_EXECUTED).
"""

#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0023WidenPoStatus [1]
#/// Исходный модуль `alembic/versions/0023_widen_po_status.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0023_widen_po_status"
down_revision = "0022_ext_api_logs"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "portfolio_operations",
        "status",
        existing_type=sa.String(20),
        type_=sa.String(128),
        existing_nullable=False
    )


def downgrade():
    op.alter_column(
        "portfolio_operations",
        "status",
        existing_type=sa.String(128),
        type_=sa.String(20),
        existing_nullable=False
    )
