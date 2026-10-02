"""Crypto funding helpers for V2 BacktestHost (parity with session_backtest R7.3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.paper_ledger import PaperLedger

CRYPTO_INSTRUMENT_TYPES = frozenset({"perpetual", "coin_futures"})


def crypto_funding_enabled(config: TradingRobotConfigV4) -> bool:
    """Funding applies to ByBit perps/coin-m futures (not stocks/futures MOEX)."""
    return config.core.instrument_type in CRYPTO_INSTRUMENT_TYPES


def instrument_category_for_config(config: TradingRobotConfigV4) -> str:
    if config.core.instrument_type == "coin_futures":
        return "inverse"
    return "linear"


def _as_utc(dt: datetime | str | None) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        raw = dt.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def funding_events_in_window(
    prev_bar_time: datetime | None,
    bar_time: datetime,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Events with funding_time in (prev_bar, bar_time]."""
    bar_dt = _as_utc(bar_time)
    if bar_dt is None:
        return []
    prev_dt = _as_utc(prev_bar_time) or datetime.min.replace(tzinfo=timezone.utc)
    out: list[dict[str, Any]] = []
    for ev in events or []:
        fdt = _as_utc(ev.get("funding_time"))
        if fdt is None:
            continue
        if prev_dt < fdt <= bar_dt:
            out.append(ev)
    return out


def resolve_funding_rate(
    events: list[dict[str, Any]],
    ev: dict[str, Any],
    *,
    mode: str = "historical",
) -> float:
    """Resolve rate for a due event (historical / average / forecast)."""
    mode_n = (mode or "historical").strip().lower()
    if mode_n == "average":
        rates = [float(e.get("funding_rate") or 0) for e in (events or [])]
        return (sum(rates) / len(rates)) if rates else 0.0
    if mode_n == "forecast":
        fdt = _as_utc(ev.get("funding_time"))
        if fdt is not None:
            for candidate in events or []:
                cdt = _as_utc(candidate.get("funding_time"))
                if cdt is not None and cdt > fdt:
                    return float(candidate.get("funding_rate") or ev.get("funding_rate") or 0)
        return float(ev.get("funding_rate") or 0)
    return float(ev.get("funding_rate") or 0)


def apply_funding_charges_for_bar(
    ledger: PaperLedger,
    *,
    funding_by_symbol: dict[str, list[dict[str, Any]]],
    prev_bar_time: datetime | None,
    bar_time: datetime,
    prices: dict[str, float],
    applied_keys: set[tuple[str, str]],
    mode: str = "historical",
) -> float:
    """
    Apply due funding charges to open positions.

    Returns total cash adjustment (negative = paid by longs when rate > 0).
    """
    if not funding_by_symbol:
        return 0.0
    total = 0.0
    for symbol, events in funding_by_symbol.items():
        sym = str(symbol or "").upper()
        due = funding_events_in_window(prev_bar_time, bar_time, events)
        for ev in due:
            fdt = _as_utc(ev.get("funding_time"))
            ft_key = fdt.isoformat() if fdt is not None else str(ev.get("funding_time"))
            dedupe = (sym, ft_key)
            if dedupe in applied_keys:
                continue
            rate = resolve_funding_rate(events, ev, mode=mode)
            mark = float(prices.get(sym) or 0)
            adjustment = ledger.apply_funding_charge(sym, rate, mark_price=mark)
            if adjustment != 0.0:
                applied_keys.add(dedupe)
                total += adjustment
    return total
