"""create dictionary table

Revision ID: 0007_create_dictionary_table
Revises: 0006_create_trading_robots
Create Date: 2026-03-17 01:00:00.000000

"""
#///EPIC Platform.ITEM Migrations.TOPIC AlembicVersions0007CreateDictionaryTable [1]
#/// Исходный модуль `alembic/versions/0007_create_dictionary_table.py` — автоматическая разметка для Obsidian Source Scanner.

from alembic import op
import sqlalchemy as sa
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA

revision = '0007_create_dictionary_table'
down_revision = '0006_create_trading_robots'
branch_labels = None
depends_on = None


def upgrade():
    # Создаём таблицу dictionary
    op.create_table(
        'dictionary',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('table_name', sa.String(length=100), nullable=False),
        sa.Column('column_name', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('num_value', sa.Integer(), nullable=True),
        sa.Column('string_value', sa.String(length=255), nullable=True),
        sa.Column('hide_from_ui', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('usercre', sa.BigInteger(), nullable=True),
        sa.Column('date_creation', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('usermod', sa.BigInteger(), nullable=True),
        sa.Column('date_modification', sa.DateTime(timezone=True), nullable=True)
    )

    # Индексы
    op.create_index('ix_dictionary_table_column', 'dictionary', ['table_name', 'column_name'])
    op.create_index('ix_dictionary_num_value', 'dictionary', ['num_value'])

    # Добавляем начальные данные
    # TOKEN STATUS
    op.execute(f"""
        INSERT INTO dictionary 
            (table_name, column_name, num_value, name, description, hide_from_ui)
        VALUES 
            ('TOKEN', 'STATUS', 0, 'Удаленный', 'Токен удален/деактивирован', 0),
            ('TOKEN', 'STATUS', 1, 'Активный', 'Токен активен и используется', 0)
    """)

    # TOKEN TYPE
    op.execute(f"""
        INSERT INTO dictionary 
            (table_name, column_name, num_value, string_value, name, description)
        VALUES 
            ('TOKEN', 'TYPE', 1, 'T-Invest', 'Т-Инвестиции', 'Токен для доступа к T-Invest API')
    """)

    # ROBOT STATUS
    op.execute(f"""
        INSERT INTO dictionary 
            (table_name, column_name, num_value, name, description)
        VALUES 
            ('ROBOT', 'STATUS', 1, 'Выключен', 'Робот остановлен'),
            ('ROBOT', 'STATUS', 2, 'Включен', 'Робот активен и работает'),
            ('ROBOT', 'STATUS', 0, 'Удален', 'Робот удален')
    """)

    # ROBOT TYPE
    op.execute(f"""
        INSERT INTO dictionary 
            (table_name, column_name, num_value, name, description)
        VALUES 
            ('ROBOT', 'TYPE', 1, 'Обновление портфеля', 'Робот для автоматического обновления данных портфеля'),
            ('ROBOT', 'TYPE', 2, 'Торговый', 'Торговый робот для автоматической торговли')
    """)


def downgrade():
    op.drop_table('dictionary')