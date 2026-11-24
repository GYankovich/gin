"""user_email / user_phone status.

Revision ID: 0088_user_contact_status
Revises: 0087_user_contact_mod

0 = off (previous contact), 1 = on (current).
Active contact stays unique per user. History rows may repeat the same value.
"""

from alembic import op

revision = "0088_user_contact_status"
down_revision = "0087_user_contact_mod"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, constraint in (
        ("user_email", "uq_user_email_user_email"),
        ("user_phone", "uq_user_phone_user_phone"),
    ):
        op.execute(
            f"""
            ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS status INTEGER NOT NULL DEFAULT 1
            """
        )
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
        op.execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {constraint}_active
                ON {table} (user_id, {('email' if table == 'user_email' else 'phone')})
                WHERE status = 1
            """
        )
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_status ON {table} (status)")

    for table_name in ("USER_EMAIL", "USER_PHONE"):
        for num_value, string_value, name, description in (
            (0, "off", "Выкл", "Контакт выключен"),
            (1, "on", "Вкл", "Контакт включён"),
        ):
            op.execute(
                f"""
                INSERT INTO dictionary
                    (table_name, column_name, num_value, string_value, name, description, hide_from_ui)
                SELECT
                    '{table_name}',
                    'STATUS',
                    {num_value},
                    '{string_value}',
                    '{name}',
                    '{description}',
                    0
                WHERE NOT EXISTS (
                    SELECT 1 FROM dictionary
                     WHERE table_name = '{table_name}'
                       AND column_name = 'STATUS'
                       AND num_value = {num_value}
                )
                """
            )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM dictionary
         WHERE table_name IN ('USER_EMAIL', 'USER_PHONE')
           AND column_name = 'STATUS'
        """
    )
    for table, column, constraint in (
        ("user_email", "email", "uq_user_email_user_email"),
        ("user_phone", "phone", "uq_user_phone_user_phone"),
    ):
        op.execute(f"DROP INDEX IF EXISTS {constraint}_active")
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_status")
        op.execute(
            f"""
            DELETE FROM {table} a
            USING {table} b
            WHERE a.user_id = b.user_id
              AND a.{column} = b.{column}
              AND a.id < b.id
            """
        )
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS status")
        op.execute(
            f"""
            ALTER TABLE {table}
                ADD CONSTRAINT {constraint} UNIQUE (user_id, {column})
            """
        )
