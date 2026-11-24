"""user.date_modification timestamptz; api_tokens.token_secret sealed.

Revision ID: 0089_token_secret
Revises: 0088_user_contact_status

token and token_secret are stored with the same Fernet seal.
The secret leaves extra_data.
"""

import json

from alembic import op
from sqlalchemy import text

revision = "0089_token_secret"
down_revision = "0088_user_contact_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE "user"
            ALTER COLUMN date_modification TYPE TIMESTAMPTZ
            USING date_modification::timestamptz
        """
    )
    op.execute("ALTER TABLE api_tokens ADD COLUMN IF NOT EXISTS token_secret TEXT NULL")

    from app.core.secret_box import seal

    bind = op.get_bind()
    rows = bind.execute(text("SELECT id, token, extra_data FROM api_tokens")).mappings()
    for row in rows:
        extra = row["extra_data"] if isinstance(row["extra_data"], dict) else {}
        secret = extra.pop("token_secret", None) or extra.pop("api_secret", None)
        extra.pop("token_secret", None)
        extra.pop("api_secret", None)
        secret_text = str(secret).strip() if secret else ""
        bind.execute(
            text(
                """
                UPDATE api_tokens
                SET token = :token,
                    token_secret = :token_secret,
                    extra_data = CAST(:extra AS jsonb)
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "token": seal(str(row["token"])) if row["token"] else row["token"],
                "token_secret": seal(secret_text) if secret_text else None,
                "extra": json.dumps(extra, ensure_ascii=False),
            },
        )


def downgrade() -> None:
    from app.core.secret_box import open_secret

    bind = op.get_bind()
    rows = bind.execute(text("SELECT id, token, token_secret, extra_data FROM api_tokens")).mappings()
    for row in rows:
        extra = row["extra_data"] if isinstance(row["extra_data"], dict) else {}
        secret = open_secret(row["token_secret"]) if row["token_secret"] else None
        if secret:
            extra = dict(extra)
            extra["token_secret"] = secret
        bind.execute(
            text(
                """
                UPDATE api_tokens
                SET token = :token,
                    extra_data = CAST(:extra AS jsonb)
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "token": open_secret(row["token"]) if row["token"] else row["token"],
                "extra": json.dumps(extra, ensure_ascii=False),
            },
        )
    op.execute("ALTER TABLE api_tokens DROP COLUMN IF EXISTS token_secret")
    op.execute(
        """
        ALTER TABLE "user"
            ALTER COLUMN date_modification TYPE DATE
            USING date_modification::date
        """
    )
