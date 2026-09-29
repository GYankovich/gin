"""Shared trading domain core for live robots and backtest.

Waves 1–4: contracts, intervals, costs, risk, brokers, market data.
Must not import ``robots`` / ``robots_v2`` except soft progress hooks in data providers.
"""

from __future__ import annotations

from app.modules.trading_core.contracts import (
    Candle,
    ExecutionMode,
    OrderIntent,
    Position,
    Signal,
)
from app.modules.trading_core.costs import TradingCosts, resolve_robot_cost_rates
from app.modules.trading_core.intervals import ResolvedInterval, resolve_strategy_interval
from app.modules.trading_core.risk import RiskDecision, RiskManager, RiskParams

__all__ = [
    "Candle",
    "ExecutionMode",
    "OrderIntent",
    "Position",
    "ResolvedInterval",
    "RiskDecision",
    "RiskManager",
    "RiskParams",
    "Signal",
    "TradingCosts",
    "resolve_robot_cost_rates",
    "resolve_strategy_interval",
]
