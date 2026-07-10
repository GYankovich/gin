"""Shared trading loop helpers — одинаковая логика портфеля для live и backtest."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from app.modules.robots.trading.contracts import Fill, Signal
from app.modules.robots.trading.engines.context import RuntimeContext


def apply_fill_to_context(
    ctx: RuntimeContext,
    sig: Signal,
    fill: Fill,
    *,
    day: Optional[date] = None,
) -> None:
    """Обновляет cash/positions/equity после исполнения (live и backtest)."""
    side = sig.side.upper()
    if side == "BUY":
        invest = fill.fill_price * fill.quantity + fill.commission
        ctx.cash -= invest
        pos = ctx.positions.get(sig.secid)
        if pos is None:
            from app.modules.robots.trading.contracts import Position

            pos = Position(
                secid=sig.secid,
                figi=sig.figi or sig.secid,
                quantity=0,
                avg_entry_price=0.0,
                side="LONG",
                opened_at=fill.ts or datetime.now(timezone.utc),
            )
            ctx.positions[sig.secid] = pos
        total_qty = pos.quantity + fill.quantity
        if total_qty > 0:
            pos.avg_entry_price = (
                (pos.avg_entry_price * pos.quantity) + (fill.fill_price * fill.quantity)
            ) / total_qty
        pos.quantity = total_qty
        pos.peak_price = max(pos.peak_price, fill.fill_price)
        pos.current_price = fill.fill_price
    else:
        pos = ctx.positions.get(sig.secid)
        if pos is None or pos.quantity <= 0:
            return
        qty = min(pos.quantity, fill.quantity)
        proceeds = fill.fill_price * qty - fill.commission
        ctx.cash += proceeds
        pnl = (fill.fill_price - pos.avg_entry_price) * qty - fill.commission
        ctx.realized_pnl += pnl
        ctx.risk.record_realized_pnl(pnl)
        pos.quantity -= qty
        if pos.quantity <= 0:
            ctx.positions.pop(sig.secid, None)

    positions_value = sum(p.current_price * p.quantity for p in ctx.positions.values())
    ctx.equity = ctx.cash + positions_value

    ctx.trade_log.append({
        "secid": sig.secid,
        "figi": sig.figi or sig.secid,
        "side": side,
        "qty": fill.quantity,
        "price": fill.fill_price,
        "commission": fill.commission,
        "ts": fill.ts.isoformat() if fill.ts else None,
        "reason": sig.reason,
        "trade_date": day.isoformat() if day else None,
        "bar_time": sig.bar_time,
    })


def signal_to_trade_dict(sig: Signal, fill: Fill, *, executed: bool = True) -> Dict[str, Any]:
    return {
        "figi": sig.figi or sig.secid,
        "side": sig.side.lower(),
        "quantity": fill.quantity,
        "price": fill.fill_price,
        "commission": fill.commission,
        "bar_time": sig.bar_time,
        "was_executed": executed,
        "reason": sig.reason,
    }


__all__ = ["apply_fill_to_context", "signal_to_trade_dict"]
