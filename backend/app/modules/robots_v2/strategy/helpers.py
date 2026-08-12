"""Signal helpers for Strategy Runtime plugins."""

from __future__ import annotations

from typing import Literal

from app.modules.robots.trading.contracts import Position, Signal


def _ticker_from_position(pos: Position) -> str:
    return str(pos.secid or pos.figi or "").upper()


def has_open_position(positions: list[Position], ticker: str) -> Position | None:
    t = ticker.upper()
    for pos in positions:
        if _ticker_from_position(pos) == t and pos.quantity > 0:
            return pos
    return None


def make_entry_signal(
    *,
    ticker: str,
    side: Literal["BUY", "SELL"],
    reason: str,
    price: float | None = None,
    strength: float | None = None,
    quantity_hint: int | None = None,
) -> Signal:
    meta: dict = {"kind": "entry"}
    if strength is not None:
        meta["strength"] = strength
    return Signal(
        secid=ticker.upper(),
        side=side,
        reason=reason,
        price_at_signal=price,
        quantity_hint=quantity_hint,
        meta=meta,
        strategy=reason.split("_")[0] if reason else None,
    )


def make_exit_signal(
    *,
    ticker: str,
    reason: str,
    price: float | None = None,
    kind: Literal["exit_strategy", "exit_grid"] = "exit_strategy",
) -> Signal:
    return Signal(
        secid=ticker.upper(),
        side="CLOSE",
        reason=reason,
        price_at_signal=price,
        meta={"kind": kind},
    )
