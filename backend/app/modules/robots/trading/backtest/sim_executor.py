from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBacktestSimExecutor [1]
#/// Исходный модуль `backend/app/modules/robots/trading/backtest/sim_executor.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Any, Dict, Optional

from app.modules.robots.trading.costs import TradingCosts, calculate_position_size


class SimExecutor:
    """Order execution simulator over historical prices."""

    @staticmethod
    def execute_buy(
        *,
        cash: float,
        price: float,
        risk_params: Dict[str, Any],
        portfolio_value: float,
        cost_kw: Dict[str, float],
        free_funds_for_sizing: Optional[float] = None,
        risk_budget_max_quantity: Optional[int] = None,
    ) -> tuple[int, float, Optional[float]]:
        max_pct = float(risk_params.get("max_position_percent", 10) or 10)
        max_rub = risk_params.get("max_position_rub")
        max_rub_f = float(max_rub) if max_rub is not None else None
        ff = float(free_funds_for_sizing) if free_funds_for_sizing is not None else float(cash)
        qty = calculate_position_size(
            portfolio_value=max(portfolio_value, 1.0),
            current_price=price,
            max_position_percent=max_pct,
            max_position_rub=max_rub_f,
            free_funds=max(ff, 0.0),
        )
        if risk_budget_max_quantity is not None and risk_budget_max_quantity > 0:
            qty = min(qty, int(risk_budget_max_quantity))
        if qty <= 0:
            return 0, cash, None
        invest = price * qty
        tc_open = TradingCosts(price, qty, is_buy=True, **cost_kw)
        comm = tc_open.calculate_commission()
        if cash < invest + comm:
            return 0, cash, None
        return qty, (cash - invest - comm), comm

