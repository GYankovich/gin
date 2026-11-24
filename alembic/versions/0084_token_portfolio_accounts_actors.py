"""token_portfolio_accounts audit actors as login text.

Revision ID: 0084_tpa_actors
Revises: 0083_drop_tpa_trading

usercre / usermod store a login (varchar 128), not a user id.
Existing numeric ids are rewritten to "user".login when possible.
"""

from alembic import op

revision = "0084_tpa_actors"
down_revision = "0083_drop_tpa_trading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("usercre", "usermod"):
        op.execute(
            f"""
            ALTER TABLE token_portfolio_accounts
                ALTER COLUMN {column} TYPE VARCHAR(128)
                USING CASE
                    WHEN {column} IS NULL THEN NULL
                    ELSE {column}::text
                END
            """
        )
        op.execute(
            f"""
            UPDATE token_portfolio_accounts tpa
               SET {column} = u.login
              FROM "user" u
             WHERE tpa.{column} ~ '^[0-9]+$'
               AND u.id = tpa.{column}::bigint
            """
        )


def downgrade() -> None:
    for column in ("usercre", "usermod"):
        op.execute(
            f"""
            UPDATE token_portfolio_accounts tpa
               SET {column} = u.id::text
              FROM "user" u
             WHERE tpa.{column} = u.login
            """
        )
        op.execute(
            f"""
            ALTER TABLE token_portfolio_accounts
                ALTER COLUMN {column} TYPE BIGINT
                USING CASE
                    WHEN {column} ~ '^[0-9]+$' THEN {column}::bigint
                    ELSE NULL
                END
            """
        )
