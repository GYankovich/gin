"""
Единый риск-менеджмент для backtest и live.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §7.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingRiskInit [1]
#/// Исходный модуль `backend/app/modules/robots/trading/risk/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

from .params import RiskParams
from .manager import RiskManager, RiskDecision

__all__ = ["RiskParams", "RiskManager", "RiskDecision"]
