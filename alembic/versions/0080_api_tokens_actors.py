"""Audit actors on api_tokens.

Revision ID: 0080_api_tokens_actors
Revises: 0079_user_pkg_actors

usercre / usermod store a login (varchar 128), not a user id.
"""

from alembic import op

revision = "0080_api_tokens_actors"
down_revision = "0079_user_pkg_actors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE api_tokens
            ADD COLUMN usercre VARCHAR(128) NULL,
            ADD COLUMN usermod VARCHAR(128) NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE api_tokens
            DROP COLUMN IF EXISTS usermod,
            DROP COLUMN IF EXISTS usercre
        """
    )
