"""
Engines — тонкие оркестраторы backtest и live торговли.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §9.

`BacktestEngine` и `LiveTradingEngine` строят сессию из тех же модулей
(`DataProvider`, `PipelineRunner`, `Strategy`, `RiskManager`, `Execution`,
`Recorder`) и крутят универсальный цикл. Это обеспечивает единое поведение
бэктеста и реальной торговли (parity), как требует BRD-ARCH-03 §1.3.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingEnginesInit [1]
#/// Исходный модуль `backend/app/modules/robots/trading/engines/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

from .context import RuntimeContext
from .backtest import BacktestEngine
from .live import LiveTradingEngine

__all__ = ["RuntimeContext", "BacktestEngine", "LiveTradingEngine"]
