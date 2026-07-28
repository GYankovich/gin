"""
Настройка подключения к базе данных.

SQL-запросы, выполняемые в контексте REST-запроса, дублируются
в rest-лог (rest_YYYY-MM-DD_HH1-HH2.log).
"""
#///EPIC Platform.ITEM Core.TOPIC BackendAppCoreDatabase [1]
#/// Исходный модуль `backend/app/core/database.py` — автоматическая разметка для Obsidian Source Scanner.

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine
from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError
from contextlib import contextmanager
from typing import Generator
import logging
from datetime import datetime, timezone

from .config import settings
from .logging_config import get_logger, get_rest_logger

logger = get_logger(__name__)
sql_logger = get_logger("sqlalchemy.engine")
sql_logger.setLevel(logging.DEBUG)
_rest_log = get_rest_logger()


def _in_rest_context() -> bool:
    """Проверяет, находимся ли мы в обработке REST-запроса."""
    try:
        from app.core.rest_logging_middleware import rest_request_ctx
        return rest_request_ctx.get(False)
    except Exception:
        return False


# ============================================================
# Логирование SQL запросов через события
# ============================================================

@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault('query_start_time', []).append(datetime.now(timezone.utc))

    sql = statement.strip()
    if not sql:
        return

    sql_oneline = ' '.join(sql.split())
    sql_logger.debug("SQL: %s", sql_oneline)

    params_str = ""
    if parameters:
        params_str = str(parameters)
        if len(params_str) > 500:
            params_str = params_str[:500] + "... (truncated)"
        sql_logger.debug("PARAMS: %s", params_str)

    if _in_rest_context():
        _rest_log.debug("    [SQL] %s", sql_oneline)
        if params_str:
            _rest_log.debug("    [SQL-PARAMS] %s", params_str)


@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start_times = conn.info.get('query_start_time', [])
    if not start_times:
        return
    start_time = start_times.pop(-1)
    duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
    sql_logger.debug("DURATION: %.2fms", duration)

    if _in_rest_context():
        _rest_log.debug("    [SQL-TIME] %.2fms", duration)


@event.listens_for(Engine, "engine_connect")
def receive_engine_connect(connection, branch):
    logger.debug("Database connection established")


@event.listens_for(Engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    logger.debug("Connection checked out from pool")


# ============================================================
# Создание engine и сессий
# ============================================================

# Создаем engine с настройками для предотвращения разрыва соединений
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=int(settings.DB_POOL_SIZE),
    max_overflow=int(settings.DB_MAX_OVERFLOW),
    pool_pre_ping=True,  # ВАЖНО: проверяет соединение перед использованием
    pool_recycle=3600,   # Пересоздавать соединения через 1 час (предотвращает таймауты)
    pool_timeout=30,     # Таймаут ожидания соединения из пула
)

# Создаем фабрику сессий
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Базовый класс для моделей
Base = declarative_base()


def looks_like_connectivity_error(exc: BaseException) -> bool:
    """
    True для обрыва TCP/маршрута/DNS к PostgreSQL (и похожих), чтобы сбросить пул соединений.
    Не использовать для «логических» ошибок SQL.
    """
    if isinstance(exc, (OperationalError, InterfaceError)):
        return True
    cur: BaseException | None = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        msg = str(cur).lower()
        if any(
            token in msg
            for token in (
                "network is unreachable",
                "connection refused",
                "could not connect to server",
                "connection timed out",
                "timeout expired",
                "connection reset",
                "server closed the connection",
                "lost connection to",
                "no route to host",
            )
        ):
            return True
        cur = cur.__cause__ or getattr(cur, "orig", None)
    return False


def try_dispose_pool_on_connectivity_error(exc: BaseException) -> None:
    """
    После длительного обрыва сети к БД в пуле могут остаться мёртвые сокеты; dispose()
    закрывает все соединения — следующий checkout откроет новые (когда маршрут снова доступен).
    """
    if not looks_like_connectivity_error(exc):
        return
    try:
        logger.warning("SQLAlchemy pool dispose after DB connectivity error: %s", exc)
        engine.dispose()
    except Exception as sub:  # noqa: BLE001
        logger.warning("engine.dispose after connectivity error failed: %s", sub)


# ============================================================
# Функции для работы с сессиями
# ============================================================

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
        try:
            db.rollback()
        except SQLAlchemyError as rb_err:
            # Соединение могло быть уже разорвано (например, после сетевой ошибки во время запроса).
            logger.warning(f"Database rollback failed: {rb_err}")
        try_dispose_pool_on_connectivity_error(e)
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
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        try_dispose_pool_on_connectivity_error(e)
        raise
    finally:
        db.close()
        logger.debug("Database context session closed")