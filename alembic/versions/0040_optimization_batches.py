"""Optimization batch runs (multi-backtest grid).

Revision ID: 0040_optimization_batches
Revises: 0039_bybit_oi_lsr_history
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0040_optimization_batches"
down_revision = "0039_bybit_oi_lsr_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "optimization_batches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("robot_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("total_candidates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("initial_capital", sa.Float(), nullable=False),
        sa.Column("overfitting_warnings", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_optimization_batches_robot_status",
        "optimization_batches",
        ["robot_id", "status"],
        schema=SCHEMA,
    )
    op.create_table(
        "optimization_batch_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("candidate_index", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("param_summary", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            [f"{SCHEMA}.optimization_batches.id"],
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_optimization_batch_items_batch",
        "optimization_batch_items",
        ["batch_id", "candidate_index"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_optimization_batch_items_run",
        "optimization_batch_items",
        ["run_id"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_optimization_batch_items_run", table_name="optimization_batch_items", schema=SCHEMA)
    op.drop_index("ix_optimization_batch_items_batch", table_name="optimization_batch_items", schema=SCHEMA)
    op.drop_table("optimization_batch_items", schema=SCHEMA)
    op.drop_index("ix_optimization_batches_robot_status", table_name="optimization_batches", schema=SCHEMA)
    op.drop_table("optimization_batches", schema=SCHEMA)
