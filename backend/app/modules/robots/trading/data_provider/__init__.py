"""
DataProvider — legacy unified-engine stack (DEPRECATED).

Prod MOEX/crypto paths use `trading/data/facade.py` (MarketDataFacade).
This package remains for `trading/engines/unified_runner.py` and `test_unified_engine.py` only.
Do not import from new application code.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingDataProviderInit [1]
#/// Исходный модуль `backend/app/modules/robots/trading/data_provider/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

from .base import DataProvider
from .historical import HistoricalDataProvider
from .live import LiveDataProvider

__all__ = ["DataProvider", "HistoricalDataProvider", "LiveDataProvider"]
