"""Store the chosen login next to a pending registration code.

Revision ID: 0070_email_confirmation_login
Revises: 0069_email_confirmation
"""

from alembic import op

revision = "0070_email_confirmation_login"
down_revision = "0069_email_confirmation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE email_confirmation
            ADD COLUMN IF NOT EXISTS login VARCHAR(128)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE email_confirmation DROP COLUMN IF EXISTS login")
