#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsInit [1]
#/// Исходный модуль `backend/app/modules/robots/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/robots/__init__.py
from .scheduler import scheduler, start_scheduler, stop_scheduler
from .service import robot_service
from .portfolio_updater.robot import PortfolioUpdaterRobot
from .common.logger import get_logger, close_logger
from .base.base_robot import BaseRobot

__all__ = [
    'scheduler',
    'start_scheduler',
    'stop_scheduler',
    'robot_service',
    'PortfolioUpdaterRobot',
    'BaseRobot',
    'get_logger',
    'close_logger'
]