"""Unify audit timestamps to creation_date / modification_date; user_token actors.

Revision ID: 0094_audit_dates
Revises: 0093_robots_dict_actors

Tables in scope:
- user, package, package_feature, token_portfolio_accounts, robots, dictionary
- api_tokens.created_at → creation_date
- user_token.created_at → creation_date + modification_date + usercre/usermod
- robot_config_history.created_at → creation_date
"""

from alembic import op

revision = "0094_audit_dates"
down_revision = "0093_robots_dict_actors"
branch_labels = None
depends_on = None

_DATE_PAIR_TABLES = (
    "package",
    "package_feature",
    "token_portfolio_accounts",
    "robots",
    "dictionary",
)


def upgrade() -> None:
    op.execute('ALTER TABLE "user" RENAME COLUMN date_creation TO creation_date')
    op.execute('ALTER TABLE "user" RENAME COLUMN date_modification TO modification_date')

    for table in _DATE_PAIR_TABLES:
        op.execute(f"ALTER TABLE {table} RENAME COLUMN date_creation TO creation_date")
        op.execute(f"ALTER TABLE {table} RENAME COLUMN date_modification TO modification_date")

    op.execute("ALTER TABLE api_tokens RENAME COLUMN created_at TO creation_date")

    op.execute("ALTER TABLE user_token RENAME COLUMN created_at TO creation_date")
    op.execute(
        """
        ALTER TABLE user_token
            ADD COLUMN IF NOT EXISTS modification_date TIMESTAMPTZ NULL,
            ADD COLUMN IF NOT EXISTS usercre VARCHAR(128) NULL,
            ADD COLUMN IF NOT EXISTS usermod VARCHAR(128) NULL
        """
    )
    op.execute(
        """
        UPDATE user_token t
           SET usercre = u.login
          FROM "user" u
         WHERE u.id = t.user_id
           AND t.usercre IS NULL
        """
    )

    op.execute(
        "ALTER TABLE robot_config_history RENAME COLUMN created_at TO creation_date"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE robot_config_history RENAME COLUMN creation_date TO created_at"
    )
    op.execute(
        """
        ALTER TABLE user_token
            DROP COLUMN IF EXISTS usermod,
            DROP COLUMN IF EXISTS usercre,
            DROP COLUMN IF EXISTS modification_date
        """
    )
    op.execute("ALTER TABLE user_token RENAME COLUMN creation_date TO created_at")
    op.execute("ALTER TABLE api_tokens RENAME COLUMN creation_date TO created_at")

    for table in reversed(_DATE_PAIR_TABLES):
        op.execute(f"ALTER TABLE {table} RENAME COLUMN modification_date TO date_modification")
        op.execute(f"ALTER TABLE {table} RENAME COLUMN creation_date TO date_creation")

    op.execute('ALTER TABLE "user" RENAME COLUMN modification_date TO date_modification')
    op.execute('ALTER TABLE "user" RENAME COLUMN creation_date TO date_creation')
