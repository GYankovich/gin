"""Per-token portfolio account membership.

Revision ID: 0077_token_portfolio_accounts
Revises: 0076_package_feature

last_token_id stays "who synced this account last" (one pointer).
token_portfolio_accounts is the list of accounts each API token can see.
"""

from alembic import op

revision = "0077_token_portfolio_accounts"
down_revision = "0076_package_feature"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_portfolio_accounts (
            token_id BIGINT NOT NULL REFERENCES api_tokens(id) ON DELETE CASCADE,
            portfolio_account_id BIGINT NOT NULL REFERENCES portfolio_accounts(id) ON DELETE CASCADE,
            linked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (token_id, portfolio_account_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_token_portfolio_accounts_account
            ON token_portfolio_accounts (portfolio_account_id)
        """
    )
    # Accounts last synced by a token stay on that token.
    op.execute(
        """
        INSERT INTO token_portfolio_accounts (token_id, portfolio_account_id)
        SELECT pa.last_token_id, pa.id
          FROM portfolio_accounts pa
          JOIN api_tokens t
            ON t.id = pa.last_token_id
           AND t.user_id = pa.user_id
         WHERE pa.last_token_id IS NOT NULL
        ON CONFLICT (token_id, portfolio_account_id) DO NOTHING
        """
    )
    # Plus the account cached on the token itself (robot / live session).
    op.execute(
        """
        INSERT INTO token_portfolio_accounts (token_id, portfolio_account_id)
        SELECT t.id, pa.id
          FROM api_tokens t
          JOIN portfolio_accounts pa
            ON pa.user_id = t.user_id
           AND pa.account_id = t.account_id
         WHERE t.account_id IS NOT NULL
           AND btrim(t.account_id) <> ''
        ON CONFLICT (token_id, portfolio_account_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_token_portfolio_accounts_account")
    op.execute("DROP TABLE IF EXISTS token_portfolio_accounts")
