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


# Strategy CLOSE reasons that may sell below break-even (failed-trade recycle).
EXITS_ALLOW_BELOW_BREAK_EVEN = frozenset({"scalper_delta_invalidation"})


def allow_strategy_exit_below_break_even(reason: str | None) -> bool:
    return (reason or "") in EXITS_ALLOW_BELOW_BREAK_EVEN


def block_exit_below_break_even(
    *,
    entry: float,
    price: float,
    side: str,
    broker_commission_rate: float | None = None,
) -> str | None:
    """Block strategy MARKET exits while price is still below break-even."""
    if entry <= 0 or price <= 0:
        return None
    from app.modules.robots.trading.costs import calculate_break_even_price

    is_long = str(side or "long").lower() in ("long", "buy")
    floor_px = calculate_break_even_price(
        entry,
        is_long=is_long,
        broker_commission_rate=float(broker_commission_rate or 0.0),
    )
    if is_long and price + 1e-9 < floor_px:
        return f"below_break_even price={price:.4f}<be={floor_px:.4f}"
    if not is_long and price > floor_px + 1e-9:
        return f"above_break_even price={price:.4f}>be={floor_px:.4f}"
    return None


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
