"""Преобразование свечей API T-Invest ↔ хранение в БД ↔ формат стратегий."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


def quotation_to_decimal(q: Optional[Dict[str, Any]]) -> Decimal:
    if not q:
        return Decimal(0)
    u = int(q.get("units", 0) or 0)
    n = int(q.get("nano", 0) or 0)
    return Decimal(u) + Decimal(n) / Decimal("1000000000")


def decimal_to_quotation(val: Decimal) -> Dict[str, int]:
    x = float(val)
    u = int(x)
    nano = int(round((x - u) * 1_000_000_000))
    return {"units": u, "nano": nano}


def parse_candle_time(t: Any) -> datetime:
    if isinstance(t, str):
        s = t.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    if isinstance(t, dict):
        sec = int(t.get("seconds", 0) or 0)
        return datetime.fromtimestamp(sec, tz=timezone.utc)
    raise ValueError(f"Unsupported candle time: {t!r}")


def api_candle_to_db_tuple(candle: Dict[str, Any], figi: str, interval: str) -> Tuple[str, str, datetime, Decimal, Decimal, Decimal, Decimal, Optional[int]]:
    ts = parse_candle_time(candle.get("time"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    o = quotation_to_decimal(candle.get("open"))
    h = quotation_to_decimal(candle.get("high"))
    l = quotation_to_decimal(candle.get("low"))
    cl = quotation_to_decimal(candle.get("close"))
    vol = candle.get("volume")
    v = int(vol) if vol is not None else None
    return figi, interval, ts, o, h, l, cl, v


def db_row_to_api_candle(row: Any) -> Dict[str, Any]:
    """row: (candle_time, open, high, low, close, volume) as from DB."""
    ts: datetime = row[0]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    iso = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "time": iso,
        "open": decimal_to_quotation(Decimal(str(row[1]))),
        "high": decimal_to_quotation(Decimal(str(row[2]))),
        "low": decimal_to_quotation(Decimal(str(row[3]))),
        "close": decimal_to_quotation(Decimal(str(row[4]))),
        "volume": int(row[5]) if row[5] is not None else 0,
        "isComplete": True,
    }
