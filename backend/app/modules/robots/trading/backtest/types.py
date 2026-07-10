"""Shared backtest types and bar/session helpers (session-based + legacy engine)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from app.modules.robots.trading.grain_seed_orchestrator import parse_force_close_time

MSK = ZoneInfo("Europe/Moscow")


def candle_time_iso(candle: Dict[str, Any]) -> str:
    t = candle.get("time")
    if isinstance(t, str):
        return t
    if isinstance(t, dict):
        return str(t.get("seconds", ""))
    return ""


def iso_to_msk_time_of_day(iso: str) -> Optional[time]:
    if not iso or len(iso) < 8:
        return None
    try:
        s = iso.replace("Z", "+00:00") if str(iso).endswith("Z") else str(iso)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(MSK).time()
    except Exception:
        return None


def bar_in_trading_session(bar_iso: str, session_start: time, session_end: time) -> bool:
    tmsk = iso_to_msk_time_of_day(bar_iso)
    if tmsk is None:
        return True
    return bool(session_start <= tmsk <= session_end)


def session_time_from_risk(value: Any, default_head: str) -> time:
    raw = str(value or default_head).strip()
    head = raw.split()[0] if raw else default_head
    return parse_force_close_time(head)


@dataclass
class BacktestResult:
    initial_capital: float
    final_equity: float
    total_return_percent: float
    max_drawdown_percent: Optional[float]
    trades: List[Dict[str, Any]] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    signals: List[Dict[str, Any]] = field(default_factory=list)
    daily_positions: List[Dict[str, Any]] = field(default_factory=list)
    cancelled: bool = False
    fee_summary: Dict[str, float] = field(default_factory=dict)
    margin_summary: Dict[str, Any] = field(default_factory=dict)


# Legacy aliases (engine.py, unified_runner)
_candle_time_iso = candle_time_iso
_bar_in_trading_session = bar_in_trading_session
_session_time_from_risk = session_time_from_risk
_iso_to_msk_time_of_day = iso_to_msk_time_of_day

__all__ = [
    "BacktestResult",
    "bar_in_trading_session",
    "candle_time_iso",
    "iso_to_msk_time_of_day",
    "session_time_from_risk",
    "_bar_in_trading_session",
    "_candle_time_iso",
    "_iso_to_msk_time_of_day",
    "_session_time_from_risk",
]
