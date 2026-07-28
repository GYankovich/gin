"""
Execution — единый интерфейс отправки ордеров (sim / live).

См. docs/BRD-ARCH-03-unified-engine-architecture.md §8.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingExecutionInit [1]
#/// Исходный модуль `backend/app/modules/robots/trading/execution/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

from .base import Execution, ExecutionResult
from .sim import SimExecution
from .service import (
    ExecutionService,
    LiveExecutionService,
    build_live_execution_service,
    execution_service_for_session,
)

__all__ = [
    "Execution",
    "ExecutionResult",
    "SimExecution",
    "ExecutionService",
    "LiveExecutionService",
    "build_live_execution_service",
    "execution_service_for_session",
]
