"""Create account_orders — shared orders registry per portfolio account.

Revision ID: 0048_account_orders
Revises: 0047_bybit_acct_id_norm
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0048_account_orders"
down_revision = "0047_bybit_acct_id_norm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS account_orders (
                id bigserial PRIMARY KEY,
                portfolio_account_id bigint NOT NULL
                    REFERENCES portfolio_accounts(id) ON DELETE CASCADE,
                robot_id bigint NULL
                    REFERENCES robots(id) ON DELETE SET NULL,
                order_id varchar(120) NULL,
                client_order_id varchar(120) NULL,
                figi varchar(32) NOT NULL,
                side varchar(10) NOT NULL,
                quantity numeric(20, 4) NOT NULL,
                price numeric(20, 4) NULL,
                filled_quantity numeric(20, 4) NULL,
                avg_fill_price numeric(20, 4) NULL,
                status varchar(32) NOT NULL DEFAULT 'pending',
                order_type varchar(16) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at timestamptz NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_account_orders_account_order_id
            ON account_orders (portfolio_account_id, order_id)
            WHERE order_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_account_orders_account_status
            ON account_orders (portfolio_account_id, status)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_account_orders_account_created
            ON account_orders (portfolio_account_id, created_at DESC)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_account_orders_robot_created
            ON account_orders (robot_id, created_at DESC)
            """
        )
    )

    # Best-effort backfill from robot_trades (skip synthetic broker_import seeds).
    op.execute(
        sa.text(
            f"""
            INSERT INTO account_orders (
                portfolio_account_id, robot_id, order_id, figi, side, quantity, price,
                filled_quantity, avg_fill_price, status, order_type, created_at, updated_at
            )
            SELECT
                pa.id,
                rt.robot_id,
                rt.order_id,
                rt.figi,
                rt.side,
                rt.quantity,
                rt.price,
                rt.filled_quantity,
                rt.avg_fill_price,
                rt.status,
                CASE
                    WHEN EXISTS (
                        SELECT 1 FROM robot_order_events e
                        WHERE e.trade_id = rt.id AND e.event_type = 'manual'
                    ) THEN 'manual'
                    ELSE 'robot'
                END AS order_type,
                rt.created_at,
                COALESCE(rt.updated_at, rt.created_at)
            FROM robot_trades rt
            JOIN robots r ON r.id = rt.robot_id
            JOIN portfolio_accounts pa
              ON pa.user_id = r.user_id
             AND pa.account_id = NULLIF(btrim(COALESCE(r.config->>'account_id', '')), '')
            WHERE rt.order_id IS NOT NULL
              AND btrim(rt.order_id) <> ''
              AND lower(rt.order_id) NOT LIKE 'broker_import:%%'
              AND NOT EXISTS (
                  SELECT 1 FROM account_orders ao
                  WHERE ao.portfolio_account_id = pa.id
                    AND ao.order_id = rt.order_id
              )
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP INDEX IF EXISTS ix_account_orders_robot_created"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS ix_account_orders_account_created"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS ix_account_orders_account_status"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS uq_account_orders_account_order_id"))
    op.execute(sa.text(f"DROP TABLE IF EXISTS account_orders"))
