"""Typed MOEX risk config for profile-based validation."""

from __future__ import annotations

from pydantic import BaseModel


class MoexRiskConfig(BaseModel):
    """MOEX risk params (type2_tinvest profile)."""
    stop_loss_percent: float = 2.0
    take_profit_percent: float = 3.0
    max_position_percent: float = 10.0
    max_position_rub: float = 50000.0
    max_daily_loss: float = 10000.0
    min_trade_amount_rub: float = 500.0
    max_drawdown_percent: float = 20.0
    risk_per_trade_pct: float = 2.0
    enforce_session_hours: bool = True
    trading_hours_start: str = "10:00 MSK"
    trading_hours_end: str = "18:45 MSK"
    allowed_weekdays: int = 31


__all__ = ["MoexRiskConfig"]
