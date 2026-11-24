"""Audit actors as login text; user gets the same audit columns.

Revision ID: 0079_user_pkg_actors
Revises: 0078_tpa_audit

usercre / usermod store a login (varchar 128), not a user id.
user.created_at becomes date_creation and keeps timestamptz.
user.date_modification is a calendar date.
"""

from alembic import op

revision = "0079_user_pkg_actors"
down_revision = "0078_tpa_audit"
branch_labels = None
depends_on = None

_BIGINT_AS_TEXT = """
CASE
    WHEN {column} IS NULL THEN NULL
    ELSE {column}::text
END
"""

_TEXT_AS_BIGINT = """
CASE
    WHEN {column} ~ '^[0-9]+$' THEN {column}::bigint
    ELSE NULL
END
"""


def _actors_to_varchar(table: str) -> None:
    for column in ("usercre", "usermod"):
        op.execute(
            f"""
            ALTER TABLE {table}
                ALTER COLUMN {column} TYPE VARCHAR(128)
                USING {_BIGINT_AS_TEXT.format(column=column)}
            """
        )


def _actors_to_bigint(table: str) -> None:
    for column in ("usercre", "usermod"):
        op.execute(
            f"""
            ALTER TABLE {table}
                ALTER COLUMN {column} TYPE BIGINT
                USING {_TEXT_AS_BIGINT.format(column=column)}
            """
        )


def upgrade() -> None:
    op.execute('ALTER TABLE "user" RENAME COLUMN created_at TO date_creation')
    op.execute(
        """
        ALTER TABLE "user"
            ADD COLUMN usercre VARCHAR(128) NULL,
            ADD COLUMN usermod VARCHAR(128) NULL,
            ADD COLUMN date_modification DATE NULL
        """
    )
    _actors_to_varchar("package")
    _actors_to_varchar("package_feature")


def downgrade() -> None:
    _actors_to_bigint("package_feature")
    _actors_to_bigint("package")
    op.execute(
        """
        ALTER TABLE "user"
            DROP COLUMN IF EXISTS date_modification,
            DROP COLUMN IF EXISTS usermod,
            DROP COLUMN IF EXISTS usercre
        """
    )
    op.execute('ALTER TABLE "user" RENAME COLUMN date_creation TO created_at')
