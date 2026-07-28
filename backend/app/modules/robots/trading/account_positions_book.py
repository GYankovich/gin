"""
Live account position book helpers.

`account_positions` is the in-session source of truth for holdings on the trading
account (signed: long > 0, short < 0). Broker refresh seeds it; every live
buy/sell adjusts it immediately.
"""

from __future__ import annotations

from typing import Dict, MutableMapping, Optional


def normalize_symbol(figi: object) -> str:
    return str(figi or "").upper().strip()


def signed_qty(book: MutableMapping[str, float], figi: str) -> float:
    key = normalize_symbol(figi)
    if key in book:
        return float(book.get(key) or 0.0)
    for k, v in book.items():
        if normalize_symbol(k) == key:
            return float(v or 0.0)
    return 0.0


def apply_trade_to_account_positions(
    book: MutableMapping[str, float],
    *,
    figi: str,
    side: str,
    quantity: float,
) -> float:
    """Apply a filled/placed BUY or SELL to the signed book. Returns new signed qty."""
    key = normalize_symbol(figi)
    qty = float(quantity or 0.0)
    if not key or qty <= 0:
        return signed_qty(book, key)
    side_u = str(side or "").upper()
    cur = signed_qty(book, key)
    if side_u == "SELL":
        new_qty = cur - qty
    elif side_u == "BUY":
        new_qty = cur + qty
    else:
        return cur
    if abs(new_qty) < 1e-12:
        book.pop(key, None)
        # drop aliases
        for alias in [k for k in list(book.keys()) if normalize_symbol(k) == key and k != key]:
            book.pop(alias, None)
        return 0.0
    book[key] = new_qty
    return new_qty


def revert_trade_on_account_positions(
    book: MutableMapping[str, float],
    *,
    figi: str,
    side: str,
    quantity: float,
) -> float:
    """Undo a previously applied trade (cancel / reject after optimistic update)."""
    side_u = str(side or "").upper()
    inv = "SELL" if side_u == "BUY" else "BUY" if side_u == "SELL" else side_u
    return apply_trade_to_account_positions(book, figi=figi, side=inv, quantity=quantity)


__all__ = [
    "normalize_symbol",
    "signed_qty",
    "apply_trade_to_account_positions",
    "revert_trade_on_account_positions",
]
