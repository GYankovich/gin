"""Планировщик роботов (BRD-ARCH-04 этап 5). Пакет `scheduling` — не путать с `robots/scheduler.py`."""

from .robot_scheduler import RobotScheduler, get_robot_scheduler
from .schedule_policy import (
    inside_schedule_window,
    schedule_dict_from_robot,
    should_start_trading_session,
)

__all__ = [
    "RobotScheduler",
    "get_robot_scheduler",
    "inside_schedule_window",
    "schedule_dict_from_robot",
    "should_start_trading_session",
]
