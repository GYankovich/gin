"""Канонические интервалы свечей (ARCH-01) и код MOEX ISS `interval`."""

from typing import Dict, Optional

# Ключ — значение в API и в колонке shared_market_candles.interval
CANONICAL_TO_MOEX: Dict[str, int] = {
    "1m": 1,
    "10m": 10,
    "1h": 60,
    "1d": 24,
    "1w": 7,
    "1M": 31,
}

SUPPORTED_CANONICAL = frozenset(CANONICAL_TO_MOEX.keys())

_ALIASES = {
    "60m": "1h",
    "1hour": "1h",
    "d1": "1d",
    "1day": "1d",
}


def moex_interval_code(canonical: str) -> int:
    c = (canonical or "").strip()
    if not c:
        raise ValueError("empty interval")
    if c in CANONICAL_TO_MOEX:
        return CANONICAL_TO_MOEX[c]
    c = _ALIASES.get(c.lower(), c)
    if c in CANONICAL_TO_MOEX:
        return CANONICAL_TO_MOEX[c]
    raise ValueError(f"unsupported interval: {canonical}")


def strategy_interval_code_to_shared_canonical(interval_code_num: int) -> Optional[str]:
    """
    Map numeric interval codes used in history-backtest / DMS to
    `shared_market_candles.interval` (ARCH-01 canonical).
    Returns None for granularities not stored in the unified table (e.g. 5m MOEX, quarter).
    """
    ic = int(interval_code_num)
    if ic == 1:
        return "1m"
    if ic == 10:
        return "10m"
    if ic == 60:
        return "1h"
    if ic == 24:
        return "1d"
    if ic == 7:
        return "1w"
    if ic == 31:
        return "1M"
    return None
