"""user_email / user_phone: creation_date, audit actors, drop valid_to.

Revision ID: 0086_user_contacts
Revises: 0085_user_status

- rename valid_from → creation_date
- add usercre / usermod VARCHAR(128)
- drop valid_to (contacts are current rows, not validity windows)
"""

from alembic import op

revision = "0086_user_contacts"
down_revision = "0085_user_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("user_email", "user_phone"):
        op.execute(f'ALTER TABLE {table} RENAME COLUMN valid_from TO creation_date')
        op.execute(
            f"""
            ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS usercre VARCHAR(128) NULL,
                ADD COLUMN IF NOT EXISTS usermod VARCHAR(128) NULL
            """
        )
        op.execute(
            f"""
            UPDATE {table} t
               SET usercre = u.login
              FROM "user" u
             WHERE u.id = t.user_id
               AND t.usercre IS NULL
            """
        )
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS valid_to")


def downgrade() -> None:
    for table in ("user_email", "user_phone"):
        op.execute(
            f"""
            ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ NULL
            """
        )
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS usermod")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS usercre")
        op.execute(f"ALTER TABLE {table} RENAME COLUMN creation_date TO valid_from")
