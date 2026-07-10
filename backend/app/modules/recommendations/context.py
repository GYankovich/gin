from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schemas import BacktestRunInsight


@dataclass
class AnalysisContext:
    robot_id: int
    strategy: str
    strategy_title: Optional[str]
    config: Dict[str, Any]
    strategy_params: Dict[str, Any]
    risk: Dict[str, Any]
    robot_status: int
    live_metrics: Optional[Dict[str, Any]]
    live_snapshot: Dict[str, Any]
    signal_execution_rate_pct: Optional[float]
    risk_events_7d: int
    successful_backtests: List[BacktestRunInsight] = field(default_factory=list)
    latest_backtest: Optional[BacktestRunInsight] = None
    best_backtest: Optional[BacktestRunInsight] = None
    best_config_snapshot: Optional[Dict[str, Any]] = None
    best_backtest_payload: Optional[Dict[str, Any]] = None
