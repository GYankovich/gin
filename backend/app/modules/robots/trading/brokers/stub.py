from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBrokersStub [1]
#/// Исходный модуль `backend/app/modules/robots/trading/brokers/stub.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.modules.robots.trading.brokers.base import BrokerFacade


class StubBrokerFacade(BrokerFacade):
    def __init__(self, broker_type: str):
        self.broker_type = broker_type

    @property
    def cache_namespace(self) -> str:
        return f"{self.broker_type}:stub"

    async def _not_implemented(self):
        raise NotImplementedError(f"Broker '{self.broker_type}' is not implemented yet")

    async def get_accounts(self) -> List[Dict[str, Any]]:
        await self._not_implemented()

    async def get_portfolio(self, account_id: str) -> Dict[str, Any]:
        await self._not_implemented()

    async def get_free_funds(self, account_id: str) -> float:
        await self._not_implemented()

    async def get_candles(self, figi: str, from_date: datetime, to_date: datetime, interval: str) -> List[Dict[str, Any]]:
        await self._not_implemented()

    async def post_order(
        self,
        figi: str,
        quantity: int,
        price: float,
        direction: str,
        account_id: str,
    ) -> Dict[str, Any]:
        await self._not_implemented()

    async def get_order_state(self, account_id: str, order_id: str) -> Dict[str, Any]:
        await self._not_implemented()

    async def post_market_order(
        self,
        figi: str,
        quantity: int,
        direction: str,
        account_id: str,
    ) -> Dict[str, Any]:
        await self._not_implemented()

    async def get_orders(self, account_id: str) -> List[Dict[str, Any]]:
        await self._not_implemented()

    async def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        await self._not_implemented()

    async def connect_websocket(self, user_id: int) -> bool:
        await self._not_implemented()

    async def subscribe_prices(self, user_id: int, figis: List[str], queue) -> Dict[str, str]:
        await self._not_implemented()

    async def unsubscribe_prices(self, user_id: int, figis: List[str], queue) -> None:
        await self._not_implemented()

    async def get_last_price(self, user_id: int, figi: str) -> Optional[float]:
        await self._not_implemented()

    async def close_websocket(self, user_id: int, queue=None) -> None:
        await self._not_implemented()

    async def close(self) -> None:
        return None
