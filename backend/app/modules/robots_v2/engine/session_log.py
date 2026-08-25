"""Session file logging + external_api_logs helpers for robots v2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging_config import register_trading_session_logger
from app.core.robot_logging import APILogger

logger = logging.getLogger(__name__)


def make_session_file_logger(robot_id: int) -> logging.LoggerAdapter:
    """Same path as v1: logs/app/{date}/robots/trading_robot/id_{id}_{HH}-{HH}.log"""
    return register_trading_session_logger(robot_id)


async def log_external_api(
    *,
    robot_id: int,
    user_id: int | None,
    token_id: int | None,
    endpoint: str,
    request_data: dict[str, Any] | None = None,
    response_data: dict[str, Any] | None = None,
    response_status: int | None = None,
    error_message: str | None = None,
    started_at: datetime | None = None,
    db: Session | None = None,
) -> None:
    """Write one row to external_api_logs (+ mirror line into trading_robot file)."""
    own_db = db is None
    session = db or SessionLocal()
    try:
        api = APILogger(
            session,
            schema="public",
            robot_type="trading",
            robot_name=f"robots_v2_{robot_id}",
            robot_version="v2",
            execution_log_id=int(robot_id),
            robot_id=int(robot_id),
            write_external_api_logs=True,
            write_robot_logs=False,
        )
        await api.log(
            endpoint=endpoint,
            request_data=request_data,
            response_data=response_data,
            response_status=response_status,
            error_message=error_message,
            token_id=token_id,
            user_id=user_id,
            started_at=started_at or datetime.now(timezone.utc),
        )
    except Exception as exc:
        logger.warning("robots_v2 external_api_logs failed robot=%s: %s", robot_id, exc)
    finally:
        if own_db:
            session.close()


class SessionActionLogger:
    """File logger for all robot actions; optional dual-publish to event bus."""

    def __init__(self, robot_id: int) -> None:
        self.robot_id = robot_id
        self._file = make_session_file_logger(robot_id)

    def info(self, message: str) -> None:
        self._file.info(message)

    def warning(self, message: str) -> None:
        self._file.warning(message)

    def error(self, message: str) -> None:
        self._file.error(message)

    def exception(self, message: str) -> None:
        self._file.exception(message)
