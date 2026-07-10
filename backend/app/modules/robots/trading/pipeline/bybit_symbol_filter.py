from __future__ import annotations

import re
from typing import Iterable, List

# Bybit dated linear/inverse contracts: BTCUSDT-25SEP26, ETH-27MAR26
_DATED_CONTRACT_SUFFIX = re.compile(
    r"-\d{1,2}(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}$",
    re.IGNORECASE,
)


def is_dated_bybit_contract(symbol: str) -> bool:
    """True for quarterly/dated futures (not perpetual USDT pairs)."""
    sym = str(symbol or "").strip().upper()
    if not sym or "-" not in sym:
        return False
    return bool(_DATED_CONTRACT_SUFFIX.search(sym))


def filter_backtest_universe_symbols(symbols: Iterable[str]) -> List[str]:
    """Drop dated contracts from historical universe pool; keep perps and spot-style tickers."""
    out: List[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = str(raw or "").strip().upper()
        if not sym or sym in seen or is_dated_bybit_contract(sym):
            continue
        seen.add(sym)
        out.append(sym)
    return out
