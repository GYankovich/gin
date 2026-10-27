"""Queue of letters waiting to be sent.

Revision ID: 0071_outbound_mail
Revises: 0070_email_confirmation_login

The row is the letter. Mailbox credentials stay in the app config.
A sender claims pending rows; auth only inserts them.
"""

from alembic import op

revision = "0071_outbound_mail"
down_revision = "0070_email_confirmation_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE outbound_mail (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NULL REFERENCES "user"(id) ON DELETE SET NULL,
            to_email VARCHAR(255) NOT NULL,
            subject VARCHAR(255) NOT NULL,
            body TEXT NOT NULL,
            purpose VARCHAR(32) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            error_code VARCHAR(64) NULL,
            error_message TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            sent_at TIMESTAMPTZ NULL,
            next_attempt_at TIMESTAMPTZ NULL,
            CONSTRAINT outbound_mail_status_check
                CHECK (status IN ('pending', 'sending', 'sent', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX outbound_mail_pending_idx
            ON outbound_mail (next_attempt_at NULLS FIRST, id)
            WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS outbound_mail")
