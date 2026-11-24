"""Drop token_portfolio_accounts.is_trading.

Revision ID: 0083_drop_tpa_trading
Revises: 0082_trading_account

The trading account belongs to the robot (config core.accountId),
not to the token-to-account link.
"""

from alembic import op

revision = "0083_drop_tpa_trading"
down_revision = "0082_trading_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_token_portfolio_accounts_one_trading")
    op.execute("ALTER TABLE token_portfolio_accounts DROP COLUMN IF EXISTS is_trading")


def downgrade() -> None:
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
