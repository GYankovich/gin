"""Session metadata on user_token (IP, UA, device, geo).

Revision ID: 0075_user_token_session_meta
Revises: 0074_outbound_preregister
"""

from alembic import op

revision = "0075_user_token_session_meta"
down_revision = "0074_outbound_preregister"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_token ADD COLUMN IF NOT EXISTS ip VARCHAR(45)")
    op.execute("ALTER TABLE user_token ADD COLUMN IF NOT EXISTS user_agent TEXT")
    op.execute("ALTER TABLE user_token ADD COLUMN IF NOT EXISTS device_label VARCHAR(128)")
    op.execute("ALTER TABLE user_token ADD COLUMN IF NOT EXISTS geo_label VARCHAR(255)")
    op.execute("ALTER TABLE user_token ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_token_user_status
            ON user_token (user_id, status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_token_user_status")
    op.execute("ALTER TABLE user_token DROP COLUMN IF EXISTS last_seen_at")
    op.execute("ALTER TABLE user_token DROP COLUMN IF EXISTS geo_label")
    op.execute("ALTER TABLE user_token DROP COLUMN IF EXISTS device_label")
    op.execute("ALTER TABLE user_token DROP COLUMN IF EXISTS user_agent")
    op.execute("ALTER TABLE user_token DROP COLUMN IF EXISTS ip")
