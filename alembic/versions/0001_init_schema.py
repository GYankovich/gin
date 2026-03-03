"""init schema

Revision ID: 0001_init_schema
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# Импортируем настройки из нового места
from app.core.config import settings

revision = "0001_init_schema"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = settings.DB_SCHEMA

# Определяем статусы токенов
class UserTokenStatus:
    ACTIVE = 1
    BLOCKED = 2
    COMPLETED = 3

def upgrade() -> None:
    # Создаем схему
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')

    # Таблица user
    op.create_table(
        "user",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("login", sa.String(length=128), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        schema=SCHEMA,
    )

    # Таблица user_email
    op.create_table(
        "user_email",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "email", name="uq_user_email_user_email"),
        schema=SCHEMA,
    )

    # Таблица user_phone
    op.create_table(
        "user_phone",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "phone", name="uq_user_phone_user_phone"),
        schema=SCHEMA,
    )

    # Таблица user_token
    op.create_table(
        "user_token",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("status", sa.Integer(), nullable=False, server_default=sa.text(str(UserTokenStatus.ACTIVE))),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    # Таблица app_config
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        schema=SCHEMA,
    )


    # Добавляем начальные данные в app_config
    op.execute(
        f"""
        INSERT INTO "{SCHEMA}".app_config (key, value, description)
        VALUES ('jwt_ttl_minutes', '60', 'Время жизни JWT токена в минутах')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    # Удаляем таблицы в обратном порядке
    op.drop_table("app_config", schema=SCHEMA)
    op.drop_table("user_token", schema=SCHEMA)
    op.drop_table("user_phone", schema=SCHEMA)
    op.drop_table("user_email", schema=SCHEMA)
    op.drop_table("user", schema=SCHEMA)

