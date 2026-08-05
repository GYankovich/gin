"""Normalize ByBit portfolio account_id: drop API-key prefix.

Old: bybit:{apiKeyHead12}:UNIFIED|FUND|COPY
New: bybit:UNIFIED|FUND|COPY

Uniqueness remains (user_id, account_id). If a user already has both
legacy and canonical ids for the same kind, keep the row with the
newest last_sync / highest id and remount children onto it.

Revision ID: 0047_bybit_acct_id_norm
Revises: 0046_pa_account_id_user_unique
"""

from alembic import op
import sqlalchemy as sa

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0047_bybit_acct_id_norm"
down_revision = "0046_pa_account_id_user_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rewrite legacy bybit:{token12}:{KIND} → bybit:{KIND} when no conflict.
    op.execute(
        sa.text(
            f"""
            UPDATE portfolio_accounts pa
            SET account_id = 'bybit:' || upper(split_part(pa.account_id, ':', 3))
            WHERE pa.account_id ~* '^bybit:[^:]+:(UNIFIED|FUND|COPY)$'
              AND NOT EXISTS (
                  SELECT 1
                  FROM portfolio_accounts other
                  WHERE other.user_id = pa.user_id
                    AND other.account_id = 'bybit:' || upper(split_part(pa.account_id, ':', 3))
                    AND other.id <> pa.id
              )
            """
        )
    )

    # Conflicts: merge legacy row into existing canonical row (same user + kind).
    # Remount child tables, then delete the legacy account row.
    for child in ("portfolio_snapshots", "portfolio_operations", "portfolio_orders"):
        op.execute(
            sa.text(
                f"""
                UPDATE {child} child
                SET account_id = canon.id
                FROM portfolio_accounts legacy
                JOIN portfolio_accounts canon
                  ON canon.user_id = legacy.user_id
                 AND canon.account_id = 'bybit:' || upper(split_part(legacy.account_id, ':', 3))
                 AND canon.id <> legacy.id
                WHERE legacy.account_id ~* '^bybit:[^:]+:(UNIFIED|FUND|COPY)$'
                  AND child.account_id = legacy.id
                """
            )
        )

    op.execute(
        sa.text(
            f"""
            DELETE FROM portfolio_accounts legacy
            WHERE legacy.account_id ~* '^bybit:[^:]+:(UNIFIED|FUND|COPY)$'
              AND EXISTS (
                  SELECT 1
                  FROM portfolio_accounts canon
                  WHERE canon.user_id = legacy.user_id
                    AND canon.account_id = 'bybit:' || upper(split_part(legacy.account_id, ':', 3))
                    AND canon.id <> legacy.id
              )
            """
        )
    )


def downgrade() -> None:
    # Irreversible: token prefix cannot be reconstructed.
    pass
