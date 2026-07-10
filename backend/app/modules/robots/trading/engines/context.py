"""
RuntimeContext — общий объект состояния торговой сессии для backtest и live.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §9.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingEnginesContext [1]
#/// Исходный модуль `backend/app/modules/robots/trading/engines/context.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.modules.robots.trading.contracts import ExecutionMode, Position
from app.modules.robots.trading.data_provider.base import DataProvider
from app.modules.robots.trading.execution.base import Execution
from app.modules.robots.trading.pipeline.runner import PipelineRunner
from app.modules.robots.trading.recorder import RuntimeRecorder
from app.modules.robots.trading.risk.manager import RiskManager
from app.modules.robots.trading.strategies.base import BaseStrategy


@dataclass
class RuntimeContext:
    """Общий контекст торговой сессии. Используется и backtest, и live engine."""

    mode: ExecutionMode
    data: DataProvider
    pipeline: PipelineRunner
    strategy: BaseStrategy
    risk: RiskManager
    execution: Execution
    recorder: RuntimeRecorder

    # --- состояние портфеля ---
    cash: float = 0.0
    equity: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    trade_log: List[Dict] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)

    # --- настройки и метаданные ---
    user_id: Optional[int] = None
    robot_id: Optional[int] = None
    run_id: Optional[int] = None
    universe: List[str] = field(default_factory=list)
    allowed_figis_by_date: Dict[str, List[str]] = field(default_factory=dict)
    robot_config: Optional[dict] = None


__all__ = ["RuntimeContext"]
