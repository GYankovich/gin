"""Live session text logs for /live UI (Postgres NOTIFY fanout).

Revision ID: 0041_robot_session_logs
Revises: 0040_optimization_batches
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0041_robot_session_logs"
down_revision = "0040_optimization_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "robot_session_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("robot_id", sa.BigInteger(), nullable=False),
        sa.Column("execution_log_id", sa.BigInteger(), nullable=True),
        sa.Column("level", sa.String(16), nullable=False, server_default="INFO"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        )
    )
    op.create_index(
        "ix_robot_session_logs_robot_id",
        "robot_session_logs",
        ["robot_id", "id"]
    )
    op.create_foreign_key(
        "fk_robot_session_logs_robot_id",
        "robot_session_logs",
        "robots",
        ["robot_id"],
        ["id"],
        ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_index("ix_robot_session_logs_robot_id", table_name="robot_session_logs")
    op.drop_table("robot_session_logs")
