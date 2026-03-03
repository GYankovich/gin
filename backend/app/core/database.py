"""
Настройка подключения к базе данных
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
import logging

from .config import settings

# Настройка логгера
logger = logging.getLogger(__name__)

# Создаем engine
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Проверять соединение перед использованием
)

# Создаем фабрику сессий
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Базовый класс для моделей
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency для FastAPI
    """
    db = SessionLocal()
    try:
        logger.debug("Database session created")
        yield db
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()
        logger.debug("Database session closed")


@contextmanager
def get_db_context():
    """
    Контекстный менеджер для использования вне FastAPI
    """
    db = SessionLocal()
    try:
        logger.debug("Database context session created")
        yield db
    except Exception as e:
        logger.error(f"Database context error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()
        logger.debug("Database context session closed")