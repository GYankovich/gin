"""Typed crypto risk config for ByBit trading profile."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CryptoRiskConfig(BaseModel):
    allow_short: bool = False
    # 0 = margin trading disabled (cash/spot-only path; no borrowed buying power).
    max_leverage: int = Field(default=1, ge=0, le=125)
    max_daily_loss: float = 3.0
    max_drawdown_percent: float = 20.0
    # Cap notional of one coin vs total broker portfolio equity.
    max_position_percent: float = 20.0
    # Min notional per order (USDT) — Stage6 MIN_TRADE_AMOUNT.
    min_trade_amount_rub: float = 5.0
    risk_per_trade_pct: float = 2.0
    # Soft TP: ignore take-profit until position age / min move (SL always allowed).
    min_hold_seconds: int = Field(default=120, ge=0, le=86_400)
    min_tp_move_bps: float = Field(default=10.0, ge=0, description="Min |price-entry|/entry in bps for TP")
    # Crypto is 24/7 — Stage6 must not apply MOEX session gates.
    enforce_session_hours: bool = False
    trading_hours_start: str = "00:00"
    trading_hours_end: str = "23:59"
    allowed_weekdays: int = 127  # Mon..Sun


__all__ = ["CryptoRiskConfig"]

