from __future__ import annotations

from typing import Any, Dict, List

COMMON_RISK_PARAMS: List[Dict[str, Any]] = [
    {"field": "risk.stop_loss_percent", "min": 0.5, "max": 5.0, "step": 0.5},
    {"field": "risk.take_profit_percent", "min": 1.0, "max": 8.0, "step": 0.5},
    {"field": "risk.max_position_percent", "min": 2.0, "max": 20.0, "step": 2.0},
    {"field": "risk.max_daily_loss", "min": 1.0, "max": 10.0, "step": 1.0},
]

STRATEGY_PARAM_RANGES: Dict[str, List[Dict[str, Any]]] = {
    "reversion_to_ma": [
        {"field": "strategy_params.ma_period", "min": 5, "max": 50, "step": 5},
        {"field": "strategy_params.deviation_pct", "min": 0.5, "max": 5.0, "step": 0.5},
        {"field": "strategy_params.rsi_period", "min": 5, "max": 30, "step": 5},
        {"field": "strategy_params.max_hold_candles", "min": 5, "max": 30, "step": 5},
    ],
    "grain_seed": [
        {"field": "strategy_params.ma_fast_period", "min": 3, "max": 20, "step": 2},
        {"field": "strategy_params.ma_slow_period", "min": 10, "max": 50, "step": 5},
        {"field": "strategy_params.gap_filter_pct", "min": 1.0, "max": 5.0, "step": 0.5},
        {"field": "strategy_params.min_profit_target_pct", "min": 0.2, "max": 1.0, "step": 0.1},
    ],
    "momentum_breakout": [
        {"field": "strategy_params.lookback_days", "min": 5, "max": 30, "step": 5},
        {"field": "strategy_params.hold_candles", "min": 5, "max": 30, "step": 5},
        {"field": "strategy_params.volume_multiplier", "min": 1.0, "max": 3.0, "step": 0.5},
    ],
}

MAX_COMBINATIONS = {"speed": 20, "full": 50}
