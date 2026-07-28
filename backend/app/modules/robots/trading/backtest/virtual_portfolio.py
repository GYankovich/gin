from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBacktestVirtualPortfolio [1]
#/// Исходный модуль `backend/app/modules/robots/trading/backtest/virtual_portfolio.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Any, Dict, List


class VirtualPortfolio:
    """Simple in-memory portfolio for backtest accounting."""

    def __init__(self, initial_capital: float):
        self.cash = float(initial_capital)

    @staticmethod
    def mark_to_market(
        *,
        cash: float,
        positions: Dict[str, Any],
        price_by_figi: Dict[str, float],
    ) -> float:
        equity = float(cash)
        for figi, pos in positions.items():
            px = float(price_by_figi.get(figi) or 0)
            if px > 0:
                equity += float(getattr(pos, "quantity", 0) or 0) * px
        return equity

    @staticmethod
    def end_of_day_positions(
        *,
        trade_date: str,
        positions: Dict[str, Any],
        price_by_figi: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for figi, pos in positions.items():
            qty = int(getattr(pos, "quantity", 0) or 0)
            entry = float(getattr(pos, "entry_price", 0) or 0)
            px = float(price_by_figi.get(figi) or 0)
            unreal = ((px - entry) * qty) if px > 0 and entry > 0 else 0.0
            out.append(
                {
                    "trade_date": trade_date,
                    "ticker": figi,
                    "quantity": qty,
                    "avg_entry_price": round(entry, 6) if entry > 0 else None,
                    "current_price": round(px, 6) if px > 0 else None,
                    "unrealized_pnl": round(unreal, 6),
                    "realized_pnl": None,
                }
            )
        return out

