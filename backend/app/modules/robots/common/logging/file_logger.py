#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsCommonLoggingFileLogger [1]
#/// Исходный модуль `backend/app/modules/robots/common/logging/file_logger.py` — автоматическая разметка для Obsidian Source Scanner.

"""
DEPRECATED: используйте app.core.logging_config.get_robot_logger.

Оставлен как тонкая обёртка для старых импортов (api_logger).
Пишет в ту же структуру:
  logs/app/{date}/robots/{type}_robot/id_{id}_{HH}-{HH}.log
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.logging_config import get_robot_logger


def get_file_logger(
    robot_type: str,
    robot_name: str,
    execution_id: Optional[int] = None,
) -> logging.LoggerAdapter:
    """Получает файловый логгер для робота (новая структура каталогов)."""
    _ = robot_name
    base = f"robots.{robot_type}"
    return get_robot_logger(base, execution_id)


def get_system_logger() -> logging.Logger:
    """Системный логгер → канал app (через root/app handler после setup_logging)."""
    return logging.getLogger("robots.system")


def set_execution_id(adapter: logging.LoggerAdapter, execution_id: int) -> None:
    if hasattr(adapter, "extra") and isinstance(adapter.extra, dict):
        adapter.extra["robot_id"] = str(execution_id)
        adapter.extra["exec_id"] = str(execution_id)


def close_file_loggers() -> None:
    """No-op: handlers живут в logging_config."""
    return None
