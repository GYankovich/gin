"""One delivery queue for mail and SMS.

Revision ID: 0072_outbound_message_channel
Revises: 0071_outbound_mail

A row is one attempt on one channel. The same event can insert
a mail row and an SMS row, and each keeps its own status.
"""

from alembic import op

revision = "0072_outbound_message_channel"
down_revision = "0071_outbound_mail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE outbound_mail RENAME TO outbound_message")
    op.execute("ALTER TABLE outbound_message RENAME COLUMN to_email TO destination")
    op.execute("ALTER TABLE outbound_message ALTER COLUMN subject DROP NOT NULL")
    op.execute(
        """
        ALTER TABLE outbound_message
            ADD COLUMN channel VARCHAR(16) NOT NULL DEFAULT 'mail'
        """
    )
    op.execute("ALTER TABLE outbound_message ALTER COLUMN channel DROP DEFAULT")
    op.execute(
        """
        ALTER TABLE outbound_message
            ADD CONSTRAINT outbound_message_channel_check
            CHECK (channel IN ('mail', 'sms'))
        """
    )
    op.execute(
        """
        ALTER TABLE outbound_message
            RENAME CONSTRAINT outbound_mail_status_check
            TO outbound_message_status_check
        """
    )
    op.execute("ALTER INDEX outbound_mail_pending_idx RENAME TO outbound_message_pending_idx")


def downgrade() -> None:
    op.execute("ALTER INDEX outbound_message_pending_idx RENAME TO outbound_mail_pending_idx")
    op.execute(
        """
        ALTER TABLE outbound_message
            RENAME CONSTRAINT outbound_message_status_check
            TO outbound_mail_status_check
        """
    )
    op.execute("ALTER TABLE outbound_message DROP CONSTRAINT outbound_message_channel_check")
    op.execute("ALTER TABLE outbound_message DROP COLUMN channel")
    op.execute("ALTER TABLE outbound_message ALTER COLUMN subject SET NOT NULL")
    op.execute("ALTER TABLE outbound_message RENAME COLUMN destination TO to_email")
    op.execute("ALTER TABLE outbound_message RENAME TO outbound_mail")
