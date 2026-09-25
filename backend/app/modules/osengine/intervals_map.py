"""Маппинг таймфреймов OsEngine ↔ cache_label GIN."""

from __future__ import annotations

from typing import Dict, Optional, Set

# OsEngine TimeFrame.ToString() → candles_cache.interval (ResolvedInterval.cache_label)
_OSENGINE_TF_TO_CACHE: Dict[str, str] = {
    "Min1": "I1",
    "Min2": "I2",
    "Min3": "I3",
    "Min5": "M5",
    "Min10": "I10",
    "Min15": "I15",
    "Min30": "I30",
    "Hour1": "I60",
    "Hour2": "I120",
    "Hour4": "I240",
    "Day": "D1",
    "Week": "I7",
    "Month": "I31",
}

_CACHE_TO_OSENGINE: Dict[str, str] = {v: k for k, v in _OSENGINE_TF_TO_CACHE.items()}

# Доп. алиасы, которые может передать ensure (сырые строки)
_CACHE_ALIASES: Dict[str, str] = {
    "1m": "I1",
    "1min": "I1",
    "m1": "I1",
    "i1": "I1",
    "5m": "M5",
    "m5": "M5",
    "10m": "I10",
    "i10": "I10",
    "15m": "I15",
    "30m": "I30",
    "1h": "I60",
    "60m": "I60",
    "i60": "I60",
    "d1": "D1",
    "day": "D1",
    "1d": "D1",
}


def normalize_cache_interval(interval: str) -> str:
    raw = (interval or "").strip()
    if not raw:
        return raw
    if raw in _CACHE_TO_OSENGINE:
        return raw
    alias = _CACHE_ALIASES.get(raw.lower().replace(" ", ""))
    if alias:
        return alias
    upper = raw.upper()
    if upper in ("M5", "D1"):
        return upper
    if upper.startswith("I") and upper[1:].isdigit():
        return f"I{int(upper[1:])}"
    return raw


def cache_interval_to_osengine_tf(interval: str) -> Optional[str]:
    norm = normalize_cache_interval(interval)
    return _CACHE_TO_OSENGINE.get(norm)


def osengine_tf_to_cache_interval(tf_name: str) -> Optional[str]:
    key = (tf_name or "").strip()
    return _OSENGINE_TF_TO_CACHE.get(key)


def known_osengine_timeframes() -> Set[str]:
    return set(_OSENGINE_TF_TO_CACHE.keys())


__all__ = [
    "cache_interval_to_osengine_tf",
    "known_osengine_timeframes",
    "normalize_cache_interval",
    "osengine_tf_to_cache_interval",
]
