"""
DEPRECATED: старый модуль логирования.
Используйте `app.core.logging_config` и `app.core.robot_logging`.
"""

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsCommonLoggingInit [1]
#/// Исходный модуль `backend/app/modules/robots/common/logging/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

from app.core.robot_logging import DatabaseLogger, APILogger, FileLogger

__all__ = ["DatabaseLogger", "APILogger", "FileLogger"]