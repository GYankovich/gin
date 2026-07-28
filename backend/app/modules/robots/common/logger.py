"""
DEPRECATED: используйте `app.core.logging_config.get_robot_logger`.
"""

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsCommonLogger [1]
#/// Исходный модуль `backend/app/modules/robots/common/logger.py` — автоматическая разметка для Obsidian Source Scanner.

from app.core.logging_config import get_robot_logger


def get_logger(robot_type: str, robot_name: str):
    return get_robot_logger(f"robots.{robot_type}.{robot_name}")


def close_logger():
    return None