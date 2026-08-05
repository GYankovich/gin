"""Unified background job queue (portfolio / heavy lanes).

Revision ID: 0037_background_jobs
Revises: 0036_api_tokens_extra_data
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0037_background_jobs"
down_revision = "0036_api_tokens_extra_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lane", sa.String(32), nullable=False),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_background_jobs_lane_status_priority",
        "background_jobs",
        ["lane", "status", "priority", "created_at"]
    )
    op.create_index(
        "ix_background_jobs_idempotency_active",
        "background_jobs",
        ["idempotency_key"],
        unique=False,
        postgresql_where=sa.text("status IN ('queued', 'running')")
    )


def downgrade() -> None:
    op.drop_index("ix_background_jobs_idempotency_active", table_name="background_jobs")
    op.drop_index("ix_background_jobs_lane_status_priority", table_name="background_jobs")
    op.drop_table("background_jobs")
