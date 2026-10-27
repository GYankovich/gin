"""Address the message by contact id and record who wrote the row.

Revision ID: 0073_outbound_message_actors
Revises: 0072_outbound_message_channel

Mail points at user_email. SMS points at user_phone.
created_* is the robot or REST that inserted the row.
updated_* is the last robot or REST that changed it.
"""

from alembic import op

revision = "0073_outbound_message_actors"
down_revision = "0072_outbound_message_channel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE outbound_message DROP COLUMN destination")
    op.execute(
        """
        ALTER TABLE outbound_message
            ADD COLUMN email_id BIGINT NULL REFERENCES user_email(id) ON DELETE SET NULL,
            ADD COLUMN phone_id BIGINT NULL REFERENCES user_phone(id) ON DELETE SET NULL,
            ADD COLUMN created_source VARCHAR(16) NOT NULL,
            ADD COLUMN created_by VARCHAR(255) NOT NULL,
            ADD COLUMN updated_source VARCHAR(16) NOT NULL,
            ADD COLUMN updated_by VARCHAR(255) NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE outbound_message
            ADD CONSTRAINT outbound_message_created_source_check
            CHECK (created_source IN ('robot', 'rest'))
        """
    )
    op.execute(
        """
        ALTER TABLE outbound_message
            ADD CONSTRAINT outbound_message_updated_source_check
            CHECK (updated_source IN ('robot', 'rest'))
        """
    )
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


def downgrade() -> None:
    op.execute("ALTER TABLE outbound_message DROP CONSTRAINT outbound_message_contact_check")
    op.execute("ALTER TABLE outbound_message DROP CONSTRAINT outbound_message_updated_source_check")
    op.execute("ALTER TABLE outbound_message DROP CONSTRAINT outbound_message_created_source_check")
    op.execute("ALTER TABLE outbound_message DROP COLUMN updated_by")
    op.execute("ALTER TABLE outbound_message DROP COLUMN updated_source")
    op.execute("ALTER TABLE outbound_message DROP COLUMN created_by")
    op.execute("ALTER TABLE outbound_message DROP COLUMN created_source")
    op.execute("ALTER TABLE outbound_message DROP COLUMN phone_id")
    op.execute("ALTER TABLE outbound_message DROP COLUMN email_id")
    op.execute("ALTER TABLE outbound_message ADD COLUMN destination VARCHAR(255) NOT NULL")
