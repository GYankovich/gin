"""ByBit runtime environment — production mainnet only."""

from __future__ import annotations


def bybit_use_testnet(*_ignored: object) -> bool:
    """Always False: GIN uses ByBit mainnet for market data, screening, and execution."""
    return False
