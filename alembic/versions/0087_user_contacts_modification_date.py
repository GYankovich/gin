"""user_email / user_phone: modification_date.

Revision ID: 0087_user_contact_mod
Revises: 0086_user_contacts
"""

from alembic import op

revision = "0087_user_contact_mod"
down_revision = "0086_user_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("user_email", "user_phone"):
        op.execute(
            f"""
            ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS modification_date TIMESTAMPTZ NULL
            """
        )


def downgrade() -> None:
    for table in ("user_email", "user_phone"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS modification_date")
