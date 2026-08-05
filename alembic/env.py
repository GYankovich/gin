"""Alembic env: public schema only, no CREATE SCHEMA."""
import sys
from pathlib import Path
from logging.config import fileConfig

#///EPIC Platform.ITEM Migrations.TOPIC Alembic Runtime Config [1]
#/// Конфигурация Alembic окружения: загрузка metadata, установка DB URL
#/// и запуск offline/online миграций для схемы проекта.
from sqlalchemy import engine_from_config, pool, text
from alembic import context

# Добавляем путь к backend
sys.path.append(str(Path(__file__).parent / "backend"))

from app.core.config import settings
from app.core.database import Base
from app.modules.auth import models  # noqa: F401
from app.modules.portfolio.models import PortfolioAccount, PortfolioSnapshot, PortfolioPosition  # noqa: F401
from app.modules.tinvest.models import ApiToken  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        connection.execute(text("SET search_path TO public"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
