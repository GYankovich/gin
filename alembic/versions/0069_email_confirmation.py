"""Pending email confirmation codes for self-registration.

Revision ID: 0069_email_confirmation
Revises: 0068_portfolio_snapshot_daily

One open code per email. The code itself is stored only as a hash.
"""

from alembic import op

revision = "0069_email_confirmation"
down_revision = "0068_portfolio_snapshot_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE email_confirmation (
            id BIGSERIAL PRIMARY KEY,
            email VARCHAR(128) NOT NULL,
            purpose VARCHAR(32) NOT NULL DEFAULT 'register',
            code_hash VARCHAR(64) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            last_sent_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT email_confirmation_email_purpose UNIQUE (email, purpose)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_confirmation")
