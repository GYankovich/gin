#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBacktestInit [1]
#/// Исходный модуль `backend/app/modules/robots/trading/backtest/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

from .engine import run_robot_backtest, run_backtest_simulation
from .broker_emulator import BrokerEmulator
from .dms_emulator import DmsEmulator
from .sim_executor import SimExecutor
from .virtual_portfolio import VirtualPortfolio
from .persistence import BacktestPersistence, BacktestPersistPayload
from .metrics import BacktestMetricsCalculator

__all__ = [
    "run_robot_backtest",
    "run_backtest_simulation",
    "BrokerEmulator",
    "DmsEmulator",
    "SimExecutor",
    "VirtualPortfolio",
    "BacktestPersistence",
    "BacktestPersistPayload",
    "BacktestMetricsCalculator",
]
