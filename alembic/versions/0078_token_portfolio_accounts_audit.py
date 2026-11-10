"""Surrogate key and audit columns on token_portfolio_accounts.

Revision ID: 0078_tpa_audit
Revises: 0077_token_portfolio_accounts

id is the primary key. (token_id, portfolio_account_id) stays unique so a token
cannot be linked to the same account twice. status is TOKEN_PORTFOLIO_ACCOUNTS.STATUS.
"""

from alembic import op

revision = "0078_tpa_audit"
down_revision = "0077_token_portfolio_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE token_portfolio_accounts DROP CONSTRAINT IF EXISTS token_portfolio_accounts_pkey"
    )
    op.execute("CREATE SEQUENCE IF NOT EXISTS token_portfolio_accounts_id_seq")
    op.execute(
        """
        ALTER TABLE token_portfolio_accounts
            ADD COLUMN IF NOT EXISTS id BIGINT
        """
    )
    op.execute(
        """
        UPDATE token_portfolio_accounts
           SET id = nextval('token_portfolio_accounts_id_seq')
         WHERE id IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE token_portfolio_accounts
            ALTER COLUMN id SET NOT NULL,
            ALTER COLUMN id SET DEFAULT nextval('token_portfolio_accounts_id_seq')
        """
    )
    op.execute(
        """
        ALTER SEQUENCE token_portfolio_accounts_id_seq
            OWNED BY token_portfolio_accounts.id
        """
    )
    op.execute(
        """
        ALTER TABLE token_portfolio_accounts
            ADD CONSTRAINT token_portfolio_accounts_pkey PRIMARY KEY (id)
        """
    )
    op.execute(
        """
        ALTER TABLE token_portfolio_accounts
            ADD CONSTRAINT uq_token_portfolio_accounts_token_account
            UNIQUE (token_id, portfolio_account_id)
        """
    )
    op.execute(
        "ALTER TABLE token_portfolio_accounts RENAME COLUMN linked_at TO date_creation"
    )
    op.execute(
        """
        ALTER TABLE token_portfolio_accounts
            ADD COLUMN status INTEGER NOT NULL DEFAULT 1,
            ADD COLUMN usercre BIGINT NULL,
            ADD COLUMN usermod BIGINT NULL,
            ADD COLUMN date_modification TIMESTAMPTZ NULL
        """
    )
    op.execute(
        """
        UPDATE token_portfolio_accounts tpa
           SET usercre = t.user_id
          FROM api_tokens t
         WHERE t.id = tpa.token_id
           AND tpa.usercre IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_token_portfolio_accounts_status
            ON token_portfolio_accounts (status)
        """
    )

    for num_value, string_value, name, description in (
        (0, "off", "Выкл", "Связь токена и счёта выключена"),
        (1, "on", "Вкл", "Связь токена и счёта включена"),
    ):
        op.execute(
            f"""
            INSERT INTO dictionary
                (table_name, column_name, num_value, string_value, name, description, hide_from_ui)
            SELECT
                'TOKEN_PORTFOLIO_ACCOUNTS',
                'STATUS',
                {num_value},
                '{string_value}',
                '{name}',
                '{description}',
                0
            WHERE NOT EXISTS (
                SELECT 1 FROM dictionary
                 WHERE table_name = 'TOKEN_PORTFOLIO_ACCOUNTS'
                   AND column_name = 'STATUS'
                   AND num_value = {num_value}
            )
            """
        )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM dictionary
         WHERE table_name = 'TOKEN_PORTFOLIO_ACCOUNTS'
           AND column_name = 'STATUS'
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_token_portfolio_accounts_status")
    op.execute(
        """
        ALTER TABLE token_portfolio_accounts
            DROP COLUMN IF EXISTS date_modification,
            DROP COLUMN IF EXISTS usermod,
            DROP COLUMN IF EXISTS usercre,
            DROP COLUMN IF EXISTS status
        """
    )
    op.execute(
        "ALTER TABLE token_portfolio_accounts RENAME COLUMN date_creation TO linked_at"
    )
    op.execute(
        """
        ALTER TABLE token_portfolio_accounts
            DROP CONSTRAINT IF EXISTS uq_token_portfolio_accounts_token_account
        """
    )
    op.execute(
        "ALTER TABLE token_portfolio_accounts DROP CONSTRAINT IF EXISTS token_portfolio_accounts_pkey"
    )
    op.execute("ALTER TABLE token_portfolio_accounts DROP COLUMN IF EXISTS id")
    op.execute(
        """
        ALTER TABLE token_portfolio_accounts
            ADD CONSTRAINT token_portfolio_accounts_pkey
            PRIMARY KEY (token_id, portfolio_account_id)
        """
    )
