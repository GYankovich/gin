"""
DEPRECATED: используйте `app.core.logging_config.get_robot_logger`.
"""

from app.core.logging_config import get_robot_logger


def get_logger(robot_type: str, robot_name: str):
    return get_robot_logger(f"robots.{robot_type}.{robot_name}")


def close_logger():
    return None