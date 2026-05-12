"""add refresh_interval to api_tokens

Revision ID: 0004_add_refresh_interval
Revises: 0003_add_portfolio_tables
Create Date: 2026-03-04 12:00:00.000000

"""
#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0004AddRefreshInterval [1]
#/// Исходный модуль `alembic/versions/0004_add_refresh_interval.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0004_add_refresh_interval'
down_revision = '0003_add_portfolio_tables'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'api_tokens',
        sa.Column('refresh_interval_minutes', sa.Integer(), nullable=False, server_default='60'),
        schema=SCHEMA
    )


def downgrade():
    op.drop_column('api_tokens', 'refresh_interval_minutes', schema=SCHEMA)