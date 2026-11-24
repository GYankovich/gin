"""Drop unused token refresh interval; mark one trading account per token.

Revision ID: 0082_trading_account
Revises: 0081_drop_token_account

is_trading is the account the user chose for live orders on that token.
At most one link per token may be true.
"""

from alembic import op

revision = "0082_trading_account"
down_revision = "0081_drop_token_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE api_tokens DROP COLUMN IF EXISTS refresh_interval_minutes")
    op.execute(
        """
        ALTER TABLE token_portfolio_accounts
            ADD COLUMN is_trading BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_token_portfolio_accounts_one_trading
            ON token_portfolio_accounts (token_id)
            WHERE is_trading
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_token_portfolio_accounts_one_trading")
    op.execute("ALTER TABLE token_portfolio_accounts DROP COLUMN IF EXISTS is_trading")
    op.execute(
        """
        ALTER TABLE api_tokens
            ADD COLUMN refresh_interval_minutes INTEGER NOT NULL DEFAULT 60
        """
    )
