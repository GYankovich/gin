"""Helpers for Live manual limit orders (direct broker path)."""

from __future__ import annotations

import re
from typing import Optional


def resolve_manual_order_quantity(
    *,
    price: float,
    quantity: Optional[float] = None,
    notional: Optional[float] = None,
) -> float:
    """Resolve order size: exactly one of quantity or notional (qty = notional / price)."""
    has_qty = quantity is not None and float(quantity) > 0
    has_notional = notional is not None and float(notional) > 0
    if has_qty and has_notional:
        raise ValueError("укажите либо quantity, либо notional")
    if not has_qty and not has_notional:
        raise ValueError("нужен quantity или notional")
    if has_qty:
        return float(quantity)
    px = float(price or 0)
    if px <= 0:
        raise ValueError("price must be > 0")
    return float(notional) / px


_RET_HINTS: dict[int, str] = {
    110007: (
        "недостаточно свободного баланса (Available Balance) для новой заявки — "
        "уменьшите сумму/qty, закройте другие позиции/ордера или пополните USDT на Unified"
    ),
    110017: "reduce-only: сторона/объём не совпадают с позицией на бирже",
    110094: "номинал ниже минимума ByBit (обычно 5 USDT) после округления лота — увеличьте сумму",
}


def format_manual_broker_reject(exc: BaseException, *, free_funds: Optional[float] = None) -> str:
    """Human-readable ByBit / broker reject text for Live manual orders."""
    raw = str(exc or "").strip() or "unknown broker error"
    code: Optional[int] = None
    m = re.search(r"retCode\s*=\s*(\d+)", raw, flags=re.IGNORECASE)
    if m:
        try:
            code = int(m.group(1))
        except ValueError:
            code = None
    if code is None:
        low = raw.lower()
        if "ab not enough" in low or "not enough for new order" in low:
            code = 110007
        elif "minimum order value" in low:
            code = 110094

    hint = _RET_HINTS.get(code) if code is not None else None
    if hint:
        msg = f"retCode={code}: {hint}"
    else:
        msg = raw
    if code == 110007 and free_funds is not None:
        msg = f"{msg}. Свободно ≈ {free_funds:g} USDT"
    return msg


__all__ = [
    "resolve_manual_order_quantity",
    "format_manual_broker_reject",
]
