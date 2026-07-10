#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsPortfolioUpdaterInit [1]
#/// Исходный модуль `backend/app/modules/robots/portfolio_updater/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/robots/portfolio_updater/__init__.py
from .robot import PortfolioUpdaterRobot
from .scheduler import PortfolioUpdaterScheduler

__all__ = [
    'PortfolioUpdaterRobot',
    'PortfolioUpdaterScheduler'
]