"""Drop api_tokens.account_id; the link table is the account list.

Revision ID: 0081_drop_token_account
Revises: 0080_api_tokens_actors

Any broker account still cached only on the token is linked first.
"""

from alembic import op

revision = "0081_drop_token_account"
down_revision = "0080_api_tokens_actors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO token_portfolio_accounts (token_id, portfolio_account_id, status)
        SELECT t.id, pa.id, 1
          FROM api_tokens t
          JOIN portfolio_accounts pa
            ON pa.user_id = t.user_id
           AND pa.account_id = t.account_id
         WHERE t.account_id IS NOT NULL
           AND btrim(t.account_id) <> ''
        ON CONFLICT (token_id, portfolio_account_id) DO NOTHING
        """
    )
    op.execute("ALTER TABLE api_tokens DROP COLUMN IF EXISTS account_id")


def downgrade() -> None:
    op.execute("ALTER TABLE api_tokens ADD COLUMN account_id VARCHAR(50) NULL")
