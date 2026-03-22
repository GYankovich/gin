"""create api_tokens table

Revision ID: 0002_create_api_tokens
Revises: 0001_init_schema
Create Date: 2026-03-02 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0002_create_api_tokens'
down_revision = '0001_init_schema'
branch_labels = None
depends_on = None

def upgrade():
    # Создаем таблицу api_tokens, если её нет
    op.create_table(
        'api_tokens',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('token', sa.Text(), nullable=False),
        sa.Column('token_type', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], [f'{SCHEMA}.user.id'], ondelete='CASCADE'),
        schema=SCHEMA,
    )
    op.create_index('ix_api_tokens_user_id', 'api_tokens', ['user_id'], schema=SCHEMA)
    op.create_index('ix_api_tokens_token_type', 'api_tokens', ['token_type'], schema=SCHEMA)
    print("✅ Table 'api_tokens' created successfully.")

def downgrade():
    op.drop_table('api_tokens', schema=SCHEMA)
    print("✅ Table 'api_tokens' dropped.")