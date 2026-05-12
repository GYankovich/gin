"""create robots table

Revision ID: 0008_create_robots_table
Revises: 0007_create_dictionary_table
Create Date: 2026-03-17 01:10:00.000000

"""
#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0008CreateRobotsTable [1]
#/// Исходный модуль `alembic/versions/0008_create_robots_table.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0008_create_robots_table'
down_revision = '0007_create_dictionary_table'
branch_labels = None
depends_on = None


def upgrade():
    # Создаём основную таблицу роботов
    op.create_table(
        'robots',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('token_id', sa.BigInteger(), nullable=True),
        sa.Column('type', sa.Integer(), nullable=False),  # ссылка на dictionary
        sa.Column('status', sa.Integer(), nullable=False, server_default='0'),  # ссылка на dictionary
        sa.Column('config', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('last_started', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_stopped', sa.DateTime(timezone=True), nullable=True),        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('usercre', sa.BigInteger(), nullable=True),
        sa.Column('date_creation', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('usermod', sa.BigInteger(), nullable=True),
        sa.Column('date_modification', sa.DateTime(timezone=True), nullable=True),

        # Foreign keys
        sa.ForeignKeyConstraint(['user_id'], [f'{SCHEMA}.user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['token_id'], [f'{SCHEMA}.api_tokens.id'], ondelete='SET NULL'),

        schema=SCHEMA,
    )

    # Индексы
    op.create_index('ix_robots_user_id', 'robots', ['user_id'], schema=SCHEMA)
    op.create_index('ix_robots_token_id', 'robots', ['token_id'], schema=SCHEMA)
    op.create_index('ix_robots_type', 'robots', ['type'], schema=SCHEMA)
    op.create_index('ix_robots_status', 'robots', ['status'], schema=SCHEMA)


def downgrade():
    op.drop_table('robots', schema=SCHEMA)