"""
DEPRECATED: старый модуль логирования.
Используйте `app.core.logging_config` и `app.core.robot_logging`.
"""

from app.core.robot_logging import DatabaseLogger, APILogger, FileLogger

__all__ = ["DatabaseLogger", "APILogger", "FileLogger"]