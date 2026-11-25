"""robots + dictionary audit actors as login text.

Revision ID: 0093_robots_dict_actors
Revises: 0092_rename_robots_v2

usercre / usermod store a login (varchar 128), not a user id.
"""

from alembic import op

revision = "0093_robots_dict_actors"
down_revision = "0092_rename_robots_v2"
branch_labels = None
depends_on = None


def _to_varchar(table: str) -> None:
    for column in ("usercre", "usermod"):
        op.execute(
            f"""
            ALTER TABLE {table}
                ALTER COLUMN {column} TYPE VARCHAR(128)
                USING CASE
                    WHEN {column} IS NULL THEN NULL
                    ELSE {column}::text
                END
            """
        )
        op.execute(
            f"""
            UPDATE {table} t
               SET {column} = u.login
              FROM "user" u
             WHERE t.{column} ~ '^[0-9]+$'
               AND u.id = t.{column}::bigint
            """
        )


def _to_bigint(table: str) -> None:
    for column in ("usercre", "usermod"):
        op.execute(
            f"""
            UPDATE {table} t
               SET {column} = u.id::text
              FROM "user" u
             WHERE t.{column} = u.login
            """
        )
        op.execute(
            f"""
            ALTER TABLE {table}
                ALTER COLUMN {column} TYPE BIGINT
                USING CASE
                    WHEN {column} ~ '^[0-9]+$' THEN {column}::bigint
                    ELSE NULL
                END
            """
        )


def upgrade() -> None:
    _to_varchar("robots")
    _to_varchar("dictionary")


def downgrade() -> None:
    _to_bigint("dictionary")
    _to_bigint("robots")
