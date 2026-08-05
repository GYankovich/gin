"""Drop global unique on portfolio_accounts.account_id.

Keep uniqueness only on (user_id, account_id) so ByBit per-token
account ids (bybit:{key12}:UNIFIED/FUND/COPY) can coexist across users.

Revision ID: 0046_pa_account_id_user_unique
Revises: 0045_portfolio_dashboard_hidden
"""

from alembic import op

from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = "0046_pa_account_id_user_unique"
down_revision = "0045_portfolio_dashboard_hidden"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Column-level UNIQUE from 0003 (account_id unique=True).
    # Name may vary; drop by inspecting if present.
    bind = op.get_bind()
    insp = __import__("sqlalchemy").inspect(bind)
    uniques = insp.get_unique_constraints("portfolio_accounts")
    for uq in uniques:
        cols = list(uq.get("column_names") or [])
        name = uq.get("name")
        if name and cols == ["account_id"]:
            op.drop_constraint(name, "portfolio_accounts", type_="unique")

    # Ensure composite unique exists (created in 0003 as uq_user_account).
    existing_names = {u.get("name") for u in uniques}
    indexes = insp.get_indexes("portfolio_accounts")
    index_names = {i.get("name") for i in indexes}
    if "uq_user_account" not in existing_names and "ix_portfolio_accounts_user_account" not in index_names:
        op.create_unique_constraint(
            "uq_user_account",
            "portfolio_accounts",
            ["user_id", "account_id"]
        )


def downgrade() -> None:
    # Restore global unique on account_id (may fail if duplicates exist).
    op.create_unique_constraint(
        "portfolio_accounts_account_id_key",
        "portfolio_accounts",
        ["account_id"]
    )
