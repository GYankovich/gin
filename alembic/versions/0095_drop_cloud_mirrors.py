"""Drop cloud migration mirrors and unused schemas.

Revision ID: 0095_drop_mirrors
Revises: 0094_audit_dates

Drops public.ganaly__* and public.backtest__* copies left after cloud→local sync.
Also drops empty schema ganaly and legacy schema backtest (canonical backtest_* stay in public).
"""

from alembic import op

revision = "0095_drop_mirrors"
down_revision = "0094_audit_dates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE r record;
        BEGIN
            FOR r IN
                SELECT quote_ident(c.relname) AS qname
                  FROM pg_class c
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public'
                   AND c.relkind = 'r'
                   AND (c.relname LIKE 'ganaly\\_\\_%' ESCAPE '\\'
                        OR c.relname LIKE 'backtest\\_\\_%' ESCAPE '\\')
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS public.' || r.qname || ' CASCADE';
            END LOOP;
        END $$;
        """
    )
    op.execute("DROP SCHEMA IF EXISTS ganaly CASCADE")
    op.execute("DROP SCHEMA IF EXISTS backtest CASCADE")


def downgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ganaly")
    op.execute("CREATE SCHEMA IF NOT EXISTS backtest")
