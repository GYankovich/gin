"""Add user.status (dictionary USER.STATUS).

Revision ID: 0085_user_status
Revises: 0084_tpa_actors

0 = off, 1 = on. Existing rows stay active.
"""

from alembic import op

revision = "0085_user_status"
down_revision = "0084_tpa_actors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE "user"
            ADD COLUMN IF NOT EXISTS status INTEGER NOT NULL DEFAULT 1
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_status ON \"user\" (status)")

    for num_value, string_value, name, description in (
        (0, "off", "Выкл", "Пользователь выключен"),
        (1, "on", "Вкл", "Пользователь включён"),
    ):
        op.execute(
            f"""
            INSERT INTO dictionary
                (table_name, column_name, num_value, string_value, name, description, hide_from_ui)
            SELECT
                'USER',
                'STATUS',
                {num_value},
                '{string_value}',
                '{name}',
                '{description}',
                0
            WHERE NOT EXISTS (
                SELECT 1 FROM dictionary
                 WHERE table_name = 'USER'
                   AND column_name = 'STATUS'
                   AND num_value = {num_value}
            )
            """
        )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM dictionary
         WHERE table_name = 'USER'
           AND column_name = 'STATUS'
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_user_status")
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS status')
