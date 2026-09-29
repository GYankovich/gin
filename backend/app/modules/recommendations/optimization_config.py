"""Optimizable parameter ranges for v4 trading configs (ARCH-05 A.2)."""

from __future__ import annotations

from typing import Any, Dict, List

# Paths use camelCase aliases as stored in robot.config JSON.
COMMON_RISK_PARAMS: List[Dict[str, Any]] = [
    {"field": "risk.stopLossPct", "min": 1.0, "max": 8.0, "step": 0.5},
    {"field": "risk.takeProfitPct", "min": 2.0, "max": 15.0, "step": 1.0},
    {"field": "risk.maxPositionSharePct", "min": 10.0, "max": 50.0, "step": 5.0},
]

STRATEGY_PARAM_RANGES: Dict[str, List[Dict[str, Any]]] = {
    "momentum": [
        {"field": "strategy.params.maPeriod", "min": 20, "max": 80, "step": 10},
        {"field": "strategy.params.volumeMultiplier", "min": 1.5, "max": 3.5, "step": 0.5},
        {"field": "strategy.params.breakoutLookback", "min": 10, "max": 40, "step": 5},
    ],
    "reversion": [
        {"field": "strategy.params.overboughtThreshold", "min": 65, "max": 85, "step": 5},
        {"field": "strategy.params.oversoldThreshold", "min": 15, "max": 35, "step": 5},
        {"field": "strategy.params.rsiPeriod", "min": 7, "max": 21, "step": 2},
    ],
    "grid": [
        {"field": "strategy.params.gridStepAtrPct", "min": 0.5, "max": 3.0, "step": 0.5},
        {"field": "strategy.params.gridDepth", "min": 3, "max": 12, "step": 1},
        {"field": "strategy.params.baseAllocationPct", "min": 15, "max": 50, "step": 5},
    ],
    # scalper: not backtestable on bars — no ranges
}

# Legacy keys kept for old snapshots in rank/insights (read-only).
LEGACY_STRATEGY_PARAM_RANGES: Dict[str, List[Dict[str, Any]]] = {
    "grain_seed": [
        {"field": "strategy_params.ma_fast_period", "min": 3, "max": 20, "step": 2},
        {"field": "strategy_params.ma_slow_period", "min": 10, "max": 50, "step": 5},
    ],
    "reversion_to_ma": [
        {"field": "strategy_params.ma_period", "min": 5, "max": 50, "step": 5},
    ],
    "momentum_breakout": [
        {"field": "strategy_params.lookback_days", "min": 5, "max": 30, "step": 5},
    ],
}

MAX_COMBINATIONS = {"speed": 20, "full": 50}
