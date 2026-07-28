"""Rename ganaly.api_tokens.is_active -> status

After this migration:
- status=1: active token
- status=0: inactive token
- status=3: expired token (written by auth-error invalidation logic)
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0043_api_tokens_status"
down_revision = "0042_token_status_expired"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add new column
    op.add_column("api_tokens", sa.Column("status", sa.Integer(), nullable=True), schema=SCHEMA)

    # 2) Backfill from legacy is_active
    op.execute(
        sa.text(
            f"""
            UPDATE {SCHEMA}.api_tokens
            SET status = CASE
                WHEN is_active = 1 THEN 1
                ELSE 0
            END
            """
        )
    )

    # 3) Make it non-null (keep default for safety)
    op.alter_column("api_tokens", "status", nullable=False, server_default=sa.text("1"), schema=SCHEMA)

    # 4) Drop legacy column
    op.drop_column("api_tokens", "is_active", schema=SCHEMA)


def downgrade() -> None:
    # Re-create is_active for rollback
    op.add_column("api_tokens", sa.Column("is_active", sa.Integer(), nullable=True), schema=SCHEMA)
    op.execute(
        sa.text(
            f"""
            UPDATE {SCHEMA}.api_tokens
            SET is_active = CASE
                WHEN status = 1 THEN 1
                ELSE 0
            END
            """
        )
    )
    op.alter_column("api_tokens", "is_active", nullable=False, server_default=sa.text("1"), schema=SCHEMA)

    op.drop_column("api_tokens", "status", schema=SCHEMA)

