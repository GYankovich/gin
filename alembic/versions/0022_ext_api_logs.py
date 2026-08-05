"""external_api_logs for broker API calls

Revision ID: 0022_ext_api_logs
Revises: 0021_pa_last_token_id
Create Date: 2026-04-13 12:00:00.000000

"""

#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0022ExtApiLogs [1]
#/// Исходный модуль `alembic/versions/0022_ext_api_logs.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings
from sqlalchemy.dialects.postgresql import JSONB

SCHEMA = settings.DB_SCHEMA

revision = "0022_ext_api_logs"
down_revision = "0021_pa_last_token_id"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "external_api_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("token_id", sa.BigInteger(), nullable=True),
        sa.Column("broker", sa.String(32), nullable=False, server_default="tinvest"),
        sa.Column("context_type", sa.String(64), nullable=True),
        sa.Column("context_ref", sa.String(128), nullable=True),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("request_data", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_data", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], [f"user.id"], ondelete="SET NULL")
    )
    op.create_index("ix_external_api_logs_user_created", "external_api_logs", ["user_id", "created_at"])
    op.create_index("ix_external_api_logs_endpoint", "external_api_logs", ["endpoint"])
    op.create_index("ix_external_api_logs_success", "external_api_logs", ["success"])
    op.create_index("ix_external_api_logs_broker", "external_api_logs", ["broker"])


def downgrade():
    op.drop_index("ix_external_api_logs_broker", table_name="external_api_logs")
    op.drop_index("ix_external_api_logs_success", table_name="external_api_logs")
    op.drop_index("ix_external_api_logs_endpoint", table_name="external_api_logs")
    op.drop_index("ix_external_api_logs_user_created", table_name="external_api_logs")
    op.drop_table("external_api_logs")
