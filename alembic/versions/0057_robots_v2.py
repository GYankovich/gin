"""robots_v2 tables for greenfield contour.

Revision ID: 0057_robots_v2
Revises: 0056_api_tokens_last_error
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0057_robots_v2"
down_revision = "0056_api_tokens_last_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "robots_v2",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_id", sa.BigInteger(), nullable=True),
        sa.Column("type", sa.Integer(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_started", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usercre", sa.BigInteger(), nullable=True),
        sa.Column("date_creation", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("usermod", sa.BigInteger(), nullable=True),
        sa.Column("date_modification", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["token_id"], ["api_tokens.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_robots_v2_user_id", "robots_v2", ["user_id"])
    op.create_index("ix_robots_v2_token_id", "robots_v2", ["token_id"])
    op.create_index("ix_robots_v2_type", "robots_v2", ["type"])
    op.create_index("ix_robots_v2_status", "robots_v2", ["status"])

    op.create_table(
        "robot_config_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("robot_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["robot_id"], ["robots_v2.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_robot_config_history_robot_id", "robot_config_history", ["robot_id"])
    op.create_index(
        "ix_robot_config_history_robot_version",
        "robot_config_history",
        ["robot_id", "version"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_robot_config_history_robot_version", table_name="robot_config_history")
    op.drop_index("ix_robot_config_history_robot_id", table_name="robot_config_history")
    op.drop_table("robot_config_history")
    op.drop_index("ix_robots_v2_status", table_name="robots_v2")
    op.drop_index("ix_robots_v2_type", table_name="robots_v2")
    op.drop_index("ix_robots_v2_token_id", table_name="robots_v2")
    op.drop_index("ix_robots_v2_user_id", table_name="robots_v2")
    op.drop_table("robots_v2")
