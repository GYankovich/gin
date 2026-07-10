"""
Универсальный пайплайн утренней фильтрации тикеров для backtest и live.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §5.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingPipelineInit [1]
#/// Исходный модуль `backend/app/modules/robots/trading/pipeline/__init__.py` — автоматическая разметка для Obsidian Source Scanner.

from .runner import PipelineRunner, PipelineResult, PipelineDecision

__all__ = ["PipelineRunner", "PipelineResult", "PipelineDecision"]
