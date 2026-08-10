"""Widen portfolio_orders / portfolio_operations ids; unique (account_id, order_id).

Revision ID: 0049_portfolio_orders_widen
Revises: 0048_account_orders
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0049_portfolio_orders_widen"
down_revision = "0048_account_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            ALTER TABLE portfolio_orders
            ALTER COLUMN order_id TYPE varchar(120)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            ALTER TABLE portfolio_operations
            ALTER COLUMN operation_id TYPE varchar(120)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            ALTER TABLE portfolio_orders
            ALTER COLUMN figi TYPE varchar(32)
            """
        )
    )
    # Prefer composite uniqueness (account, order_id) over global order_id alone.
    op.execute(
        sa.text(
            f"""
            ALTER TABLE portfolio_orders
            DROP CONSTRAINT IF EXISTS portfolio_orders_order_id_key
            """
        )
    )
    op.execute(
        sa.text(
            f"DROP INDEX IF EXISTS ix_portfolio_orders_order_id"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_orders_account_order_id
            ON portfolio_orders (account_id, order_id)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_portfolio_orders_account_status
            ON portfolio_orders (account_id, status)
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP INDEX IF EXISTS ix_portfolio_orders_account_status"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS uq_portfolio_orders_account_order_id"))
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_portfolio_orders_order_id
            ON portfolio_orders (order_id)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            ALTER TABLE portfolio_orders
            ALTER COLUMN figi TYPE varchar(20)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            ALTER TABLE portfolio_operations
            ALTER COLUMN operation_id TYPE varchar(50)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            ALTER TABLE portfolio_orders
            ALTER COLUMN order_id TYPE varchar(50)
            """
        )
    )
