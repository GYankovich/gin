"""Isolated-margin helpers for crypto backtest simulation."""

from __future__ import annotations

from typing import Any, Dict, Optional


def resolve_margin_params(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve margin settings.

    leverage=0 means margin trading is disabled (no borrowed buying power).
    leverage>0 enables margin for non-spot ByBit categories at that leverage.
    """
    cfg = config or {}
    broker = str(cfg.get("broker_type") or "tinvest").strip().lower()
    bybit = cfg.get("bybit") if isinstance(cfg.get("bybit"), dict) else {}
    risk = cfg.get("risk") if isinstance(cfg.get("risk"), dict) else {}
    category = str(bybit.get("instrument_category") or "linear").strip().lower()
    if "leverage" in bybit and bybit.get("leverage") is not None:
        leverage = float(bybit.get("leverage"))
    elif risk.get("max_leverage") is not None:
        leverage = float(risk.get("max_leverage"))
    else:
        leverage = 1.0
    mmr = float(bybit.get("maintenance_margin_rate") or 0.005)
    enabled = broker == "bybit" and category != "spot" and leverage > 0
    return {
        "enabled": enabled,
        "leverage": float(leverage),
        "maintenance_margin_rate": max(0.0, mmr),
        "category": category,
    }


def initial_margin(notional: float, leverage: float) -> float:
    return float(notional) / max(float(leverage), 1.0)


def liquidation_price_long(entry_price: float, leverage: float, maintenance_margin_rate: float) -> float:
    """USDT-linear isolated long (simplified ByBit-style)."""
    entry = float(entry_price)
    if entry <= 0:
        return 0.0
    lev = max(float(leverage), 1.0)
    mmr = max(float(maintenance_margin_rate), 0.0)
    return max(0.0, entry * (1.0 - 1.0 / lev + mmr))


def liquidation_price_short(entry_price: float, leverage: float, maintenance_margin_rate: float) -> float:
    entry = float(entry_price)
    if entry <= 0:
        return 0.0
    lev = max(float(leverage), 1.0)
    mmr = max(float(maintenance_margin_rate), 0.0)
    return entry * (1.0 + 1.0 / lev - mmr)


def is_liquidated_long(mark_price: float, entry_price: float, leverage: float, mmr: float) -> bool:
    liq = liquidation_price_long(entry_price, leverage, mmr)
    return liq > 0 and float(mark_price) <= liq


__all__ = [
    "initial_margin",
    "is_liquidated_long",
    "liquidation_price_long",
    "liquidation_price_short",
    "resolve_margin_params",
]
