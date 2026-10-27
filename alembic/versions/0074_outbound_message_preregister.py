"""Allow a registration letter before the account exists.

Revision ID: 0074_outbound_preregister
Revises: 0073_outbound_message_actors

Login and reset point at user_email. Registration has no contact card yet,
so that letter keeps the address in to_email until the account appears.
"""

from alembic import op

revision = "0074_outbound_preregister"
down_revision = "0073_outbound_message_actors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE outbound_message ADD COLUMN to_email VARCHAR(255) NULL")
    op.execute("ALTER TABLE outbound_message DROP CONSTRAINT outbound_message_contact_check")
    op.execute(
        """
        ALTER TABLE outbound_message
            ADD CONSTRAINT outbound_message_contact_check
            CHECK (
                (
                    channel = 'mail'
                    AND phone_id IS NULL
                    AND (
                        (email_id IS NOT NULL AND to_email IS NULL)
                        OR (email_id IS NULL AND to_email IS NOT NULL)
                    )
                )
                OR
                (
                    channel = 'sms'
                    AND phone_id IS NOT NULL
                    AND email_id IS NULL
                    AND to_email IS NULL
                )
            )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE outbound_message DROP CONSTRAINT outbound_message_contact_check")
    op.execute("ALTER TABLE outbound_message DROP COLUMN to_email")
    op.execute(
        """
        ALTER TABLE outbound_message
            ADD CONSTRAINT outbound_message_contact_check
            CHECK (
                (channel = 'mail' AND email_id IS NOT NULL AND phone_id IS NULL)
                OR
                (channel = 'sms' AND phone_id IS NOT NULL AND email_id IS NULL)
            )
        """
    )
