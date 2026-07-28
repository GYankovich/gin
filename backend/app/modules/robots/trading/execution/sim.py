"""
SimExecution — симуляция исполнения для бэктеста.

Использует существующие `BrokerEmulator` (цена исполнения) и `SimExecutor`
(размер позиции с учётом cash + комиссий), чтобы поведение совпадало с
текущим `engine.py:run_backtest_simulation` (parity guard).

См. docs/BRD-ARCH-03-unified-engine-architecture.md §8.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingExecutionSim [1]
#/// Исходный модуль `backend/app/modules/robots/trading/execution/sim.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.modules.robots.trading.backtest.broker_emulator import BrokerEmulator
from app.modules.robots.trading.contracts import Fill, Order
from app.modules.robots.trading.costs import TradingCosts
from app.modules.robots.trading.execution.base import Execution, ExecutionResult


class SimExecution(Execution):
    """Сим-исполнение через `BrokerEmulator` + комиссии из `TradingCosts`.

    `submit(order, series=[...], index=N)` ожидает контекст со списком свечей
    `series` (T-Invest dict-format) и индексом текущей `index`. Цена выходит из
    `BrokerEmulator.execution_price`.
    """

    def __init__(
        self,
        *,
        execution_model: str = "NEXT_BAR_OPEN",
        slippage_pct: float = 0.0,
        commission_rate: float = 0.0005,
        ndfl_rate: float = 0.13,
    ):
        self.emulator = BrokerEmulator(execution_model=execution_model, slippage_pct=slippage_pct)
        self.commission_rate = float(commission_rate)
        self.ndfl_rate = float(ndfl_rate)

    async def submit(self, order: Order, **context) -> ExecutionResult:
        series: List[Dict[str, Any]] = list(context.get("series") or [])
        index: int = int(context.get("index") or 0)
        # цена исполнения по политике эмулятора
        price = self.emulator.execution_price(side=order.side, series=series, index=index)
        if price <= 0:
            order.status = "REJECTED"
            order.reject_reason = "no_execution_price"
            return ExecutionResult(order=order, fill=None, accepted=False, reject_reason="no_execution_price")

        # фиксируем фактическую цену в ордере
        order.price = price
        order.status = "FILLED"

        # комиссия
        tc = TradingCosts(
            price,
            order.quantity,
            is_buy=(order.side == "BUY"),
            broker_commission_rate=self.commission_rate,
            ndfl_rate=self.ndfl_rate,
        )
        comm = tc.calculate_commission()

        fill = Fill(
            order_id=order.order_id,
            fill_price=price,
            quantity=int(order.quantity),
            commission=float(comm),
            slippage=float(self.emulator.slippage_pct),
            ts=datetime.now(timezone.utc),
        )
        return ExecutionResult(order=order, fill=fill, accepted=True)


__all__ = ["SimExecution"]
