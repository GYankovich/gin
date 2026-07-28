from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBacktestBrokerEmulator [1]
#/// Исходный модуль `backend/app/modules/robots/trading/backtest/broker_emulator.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Any, Dict, List, Optional


def _price(field: str, candle: Optional[Dict[str, Any]]) -> float:
    if not candle:
        return 0.0
    v = candle.get(field) or {}
    try:
        return float(int(v.get("units", 0) or 0)) + float(int(v.get("nano", 0) or 0)) / 1e9
    except Exception:
        return 0.0


class BrokerEmulator:
    """Historical execution price emulator (no broker API calls)."""

    def __init__(
        self,
        execution_model: str = "NEXT_BAR_OPEN",
        slippage_pct: float = 0.0,
        latency_bars: int = 0,
    ):
        self.execution_model = str(execution_model or "NEXT_BAR_OPEN").upper()
        self.slippage_pct = max(0.0, float(slippage_pct or 0.0))
        self.latency_bars = max(0, int(latency_bars or 0))

    def execution_price(
        self,
        *,
        side: str,
        series: List[Dict[str, Any]],
        index: int,
    ) -> float:
        side_u = str(side or "").upper()
        cur = series[index] if 0 <= index < len(series) else None

        if self.execution_model == "CURRENT_BAR_CLOSE":
            base = _price("close", cur)
        elif self.execution_model == "SIGNAL_BAR_HIGH_LOW":
            base = _price("high", cur) if side_u == "BUY" else _price("low", cur)
        else:  # NEXT_BAR_OPEN
            offset = 1 + self.latency_bars
            nxt = series[index + offset] if (index + offset) < len(series) else None
            base = _price("open", nxt)

        if base <= 0:
            return 0.0
        if side_u == "BUY":
            return base * (1.0 + self.slippage_pct / 100.0)
        return base * (1.0 - self.slippage_pct / 100.0)

