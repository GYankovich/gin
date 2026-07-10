from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBrokersBase [1]
#/// Исходный модуль `backend/app/modules/robots/trading/brokers/base.py` — автоматическая разметка для Obsidian Source Scanner.

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional


class BrokerFacade(ABC):
    """Abstract broker facade used by trading stages."""

    broker_type: str = "unknown"

    @property
    @abstractmethod
    def cache_namespace(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def auth_token(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get_accounts(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_portfolio(self, account_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    async def get_operations(
        self,
        account_id: str,
        from_dt: datetime,
        to_dt: datetime,
        *,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """Broker operations in T-Invest-compatible shape for portfolio_operations upsert.

        Default: no operations (stubs / brokers without history).
        """
        _ = (account_id, from_dt, to_dt, max_pages)
        return []

    @abstractmethod
    async def get_free_funds(self, account_id: str) -> float:
        raise NotImplementedError

    @abstractmethod
    async def get_candles(
        self,
        figi: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def post_order(
        self,
        figi: str,
        quantity: int,
        price: float,
        direction: str,
        account_id: str,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_order_state(self, account_id: str, order_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def post_market_order(
        self,
        figi: str,
        quantity: int,
        direction: str,
        account_id: str,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_orders(self, account_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def connect_websocket(self, user_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def subscribe_prices(self, user_id: int, figis: List[str], queue, candle_interval: Optional[str] = None) -> Dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe_prices(self, user_id: int, figis: List[str], queue) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_last_price(self, user_id: int, figi: str) -> Optional[float]:
        raise NotImplementedError

    @abstractmethod
    async def close_websocket(self, user_id: int, queue=None) -> None:
        raise NotImplementedError

    async def force_resubscribe_websocket(self, user_id: int) -> bool:
        return False

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
