"""Per-robot paper ledger (ADR-03) — long + short for crypto parity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.modules.robots.trading.contracts import Position


@dataclass
class PaperPosition:
    ticker: str
    side: str  # LONG | SHORT
    quantity: int
    avg_entry_price: float
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_long(self) -> bool:
        return self.side.upper() in ("LONG", "BUY")

    def to_position(self, current_price: float) -> Position:
        return Position(
            side="LONG" if self.is_long else "SHORT",
            quantity=self.quantity,
            avg_entry_price=self.avg_entry_price,
            secid=self.ticker,
            current_price=current_price,
            opened_at=self.opened_at,
        )

    def to_dict(self, current_price: float) -> dict[str, Any]:
        # RiskManager SL/TP exit side expects "sell" for shorts.
        side_out = "long" if self.is_long else "sell"
        return {
            "ticker": self.ticker,
            "figi": self.ticker,
            "side": side_out,
            "quantity": self.quantity,
            "entry_price": self.avg_entry_price,
            "current_price": current_price,
            "opened_at": self.opened_at.isoformat(),
        }


class PaperLedger:
    def __init__(self, *, cash: float, commission_rate: float = 0.0005, allow_short: bool = False) -> None:
        self.initial_cash = float(cash)
        self.cash = float(cash)
        self.commission_rate = commission_rate
        self.allow_short = allow_short
        self.positions: dict[str, PaperPosition] = {}
        self.realized_pnl: float = 0.0

    def mark_equity(self, prices: dict[str, float]) -> float:
        total = self.cash
        for t, p in self.positions.items():
            px = prices.get(t, p.avg_entry_price)
            if p.is_long:
                total += p.quantity * px
            else:
                # Short proceeds already in cash at open → subtract current liability.
                total -= p.quantity * px
        return total

    @property
    def equity(self) -> float:
        # Without marks, use entry (unrealized ≈ 0).
        return self.mark_equity({})

    def positions_dict(self, prices: dict[str, float]) -> dict[str, Position]:
        out: dict[str, Position] = {}
        for t, p in self.positions.items():
            px = prices.get(t, p.avg_entry_price)
            out[t] = p.to_position(px)
        return out

    def open_positions_list(self, prices: dict[str, float]) -> list[dict[str, Any]]:
        return [p.to_dict(prices.get(t, p.avg_entry_price)) for t, p in self.positions.items()]

    def apply_fill(
        self,
        *,
        ticker: str,
        side: str,
        quantity: int,
        price: float,
        reduce_only: bool = False,
    ) -> float:
        t = ticker.upper()
        qty = int(quantity)
        if qty <= 0 or price <= 0:
            return 0.0
        notional = price * qty
        commission = notional * self.commission_rate
        pnl = 0.0
        side_u = side.upper()
        pos = self.positions.get(t)

        if side_u == "BUY":
            # Close short
            if pos is not None and not pos.is_long:
                close_qty = min(qty, pos.quantity)
                if close_qty <= 0:
                    return 0.0
                close_notional = price * close_qty
                close_commission = close_notional * self.commission_rate
                pnl = (pos.avg_entry_price - price) * close_qty - close_commission
                self.cash -= close_notional + close_commission
                self.realized_pnl += pnl
                pos.quantity -= close_qty
                if pos.quantity <= 0:
                    del self.positions[t]
                return pnl

            if reduce_only:
                return 0.0

            # Open / add long
            self.cash -= notional + commission
            if pos is not None and pos.is_long:
                total_qty = pos.quantity + qty
                pos.avg_entry_price = (pos.avg_entry_price * pos.quantity + price * qty) / total_qty
                pos.quantity = total_qty
            else:
                self.positions[t] = PaperPosition(ticker=t, side="LONG", quantity=qty, avg_entry_price=price)
            return 0.0

        # SELL
        if pos is not None and pos.is_long:
            close_qty = min(qty, pos.quantity)
            if close_qty <= 0:
                return 0.0
            close_notional = price * close_qty
            close_commission = close_notional * self.commission_rate
            pnl = (price - pos.avg_entry_price) * close_qty - close_commission
            self.cash += close_notional - close_commission
            self.realized_pnl += pnl
            pos.quantity -= close_qty
            if pos.quantity <= 0:
                del self.positions[t]
            return pnl

        if reduce_only:
            return 0.0

        if not self.allow_short:
            return 0.0

        # Open / add short
        self.cash += notional - commission
        if pos is not None and not pos.is_long:
            total_qty = pos.quantity + qty
            pos.avg_entry_price = (pos.avg_entry_price * pos.quantity + price * qty) / total_qty
            pos.quantity = total_qty
        else:
            self.positions[t] = PaperPosition(ticker=t, side="SHORT", quantity=qty, avg_entry_price=price)
        return 0.0

    def replace_state(
        self,
        *,
        cash: float,
        positions: dict[str, PaperPosition],
    ) -> None:
        """Overwrite cash + positions (ADR-11 broker source of truth)."""
        self.cash = float(cash)
        self.positions = {str(k).upper(): v for k, v in positions.items()}
