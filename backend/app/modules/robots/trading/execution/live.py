"""
LiveExecution — отправка ордеров через `BrokerFacade`.

Тонкая обёртка над `BrokerFacade.post_order` / `post_market_order` /
`get_order_state`. Логика повторяет `Stage6Orders.execute_signals` без её
specific-обвязки (rate limit, retry — в самом BrokerFacade/TInvestFacade).

См. docs/BRD-ARCH-03-unified-engine-architecture.md §8.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingExecutionLive [1]
#/// Исходный модуль `backend/app/modules/robots/trading/execution/live.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.contracts import Fill, Order
from app.modules.robots.trading.execution.base import Execution, ExecutionResult


class LiveExecution(Execution):
    """Реальная отправка ордеров через BrokerFacade.

    На submit:
    - LIMIT → `broker.post_order(figi, qty, side, price, ...)`
    - MARKET → `broker.post_market_order(figi, qty, side, ...)`

    Возвращает ExecutionResult с обновлённым order (status, broker_order_id).
    Fill заполняется только если брокер уже сообщил статус FILL; иначе fill=None
    и потребитель должен следить за статусом через `on_state_changed`.
    """

    def __init__(
        self,
        broker: BrokerFacade,
        *,
        account_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ):
        self.broker = broker
        self.account_id = account_id
        self.user_id = user_id

    async def submit(self, order: Order, **context) -> ExecutionResult:
        figi = order.figi or order.secid
        if not figi or order.quantity <= 0:
            order.status = "REJECTED"
            order.reject_reason = "invalid_order"
            return ExecutionResult(order=order, fill=None, accepted=False, reject_reason="invalid_order")

        try:
            if order.type == "MARKET":
                resp = await self.broker.post_market_order(
                    account_id=self.account_id,
                    figi=figi,
                    quantity=int(order.quantity),
                    direction=order.side,
                )
            else:
                resp = await self.broker.post_order(
                    account_id=self.account_id,
                    figi=figi,
                    quantity=int(order.quantity),
                    direction=order.side,
                    price=float(order.price or 0.0),
                )
        except Exception as e:
            order.status = "REJECTED"
            order.reject_reason = f"broker_error: {e}"
            return ExecutionResult(order=order, fill=None, accepted=False, reject_reason=str(e))

        # извлекаем broker order id
        if isinstance(resp, dict):
            broker_oid = (
                resp.get("orderId")
                or resp.get("order_id")
                or resp.get("id")
                or resp.get("broker_order_id")
            )
        else:
            broker_oid = None
        order.broker_order_id = str(broker_oid) if broker_oid else None
        order.status = "NEW"

        # если ответ содержит фактическое исполнение — формируем Fill
        fill: Optional[Fill] = None
        if isinstance(resp, dict) and (resp.get("status") or "").lower() in {"filled", "fill"}:
            try:
                qty_filled = int(resp.get("lots_executed") or resp.get("quantity") or order.quantity)
                exec_price = float(resp.get("executed_price") or resp.get("price") or order.price or 0.0)
                fill = Fill(
                    order_id=order.order_id,
                    fill_price=exec_price,
                    quantity=qty_filled,
                    commission=float(resp.get("commission") or 0.0),
                    ts=datetime.now(timezone.utc),
                )
                order.status = "FILLED"
            except Exception:
                fill = None
        return ExecutionResult(order=order, fill=fill, accepted=True)

    async def cancel(self, order_id: UUID) -> bool:
        try:
            await self.broker.cancel_order(self.account_id, str(order_id))
            return True
        except Exception:
            return False


__all__ = ["LiveExecution"]
