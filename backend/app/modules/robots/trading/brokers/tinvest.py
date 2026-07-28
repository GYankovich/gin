from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBrokersTinvest [1]
#/// Исходный модуль `backend/app/modules/robots/trading/brokers/tinvest.py` — автоматическая разметка для Obsidian Source Scanner.

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.logging_config import get_logger
from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.brokers.global_websocket import global_websocket_manager
from app.modules.robots.trading.brokers.rate_limiter import get_token_rate_limiter
from app.modules.tinvest.facade import TInvestFacade

logger = get_logger(__name__)


class TInvestBrokerFacade(BrokerFacade):
    broker_type = "tinvest"

    def __init__(self, token: str):
        self._token = token
        self._facade = TInvestFacade(token)

    @property
    def cache_namespace(self) -> str:
        return f"{self.broker_type}:{self._token[:12]}"

    @property
    def auth_token(self) -> str:
        return self._token

    async def _rest_call(self, func, *args, **kwargs):
        limiter = await get_token_rate_limiter(self._token)
        waited = await limiter.acquire()
        if waited > 0:
            logger.info("Rate limit wait %.2fs for token", waited)

        last_exc: Optional[Exception] = None
        for attempt in range(1, 5):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                text = str(exc)
                if "429" not in text and "limit" not in text.lower():
                    raise
                delay = min(8, 2 ** (attempt - 1))
                logger.warning("429/rate limit response, retry in %ss (attempt %s)", delay, attempt)
                await asyncio.sleep(delay)
        raise last_exc

    async def get_accounts(self) -> List[Dict[str, Any]]:
        return await self._rest_call(self._facade.get_accounts)

    async def get_portfolio(self, account_id: str) -> Dict[str, Any]:
        return await self._rest_call(self._facade.get_portfolio, account_id)

    async def get_operations(
        self,
        account_id: str,
        from_dt: datetime,
        to_dt: datetime,
        *,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        payload = await self._rest_call(
            self._facade.rest.get_operations_all_pages,
            account_id,
            from_dt,
            to_dt,
            max_pages=max_pages,
        )
        return list((payload or {}).get("operations") or [])

    async def get_free_funds(self, account_id: str) -> float:
        return await self._rest_call(self._facade.get_free_funds, account_id)

    async def get_candles(self, figi: str, from_date: datetime, to_date: datetime, interval: str) -> List[Dict[str, Any]]:
        return await self._rest_call(self._facade.get_candles, figi, from_date, to_date, interval)

    async def post_order(
        self,
        figi: str,
        quantity: int,
        price: float,
        direction: str,
        account_id: str,
        *,
        reduce_only: bool = False,
        qty_round_up: bool = False,
    ) -> Dict[str, Any]:
        del reduce_only, qty_round_up  # T-Invest close path does not use reduceOnly / round-up
        return await self._rest_call(self._facade.post_order, figi, int(quantity), price, direction, account_id)

    async def get_order_state(self, account_id: str, order_id: str) -> Dict[str, Any]:
        return await self._rest_call(self._facade.get_order_state, account_id, order_id)

    async def post_market_order(
        self,
        figi: str,
        quantity: int,
        direction: str,
        account_id: str,
    ) -> Dict[str, Any]:
        return await self._rest_call(
            self._facade.post_market_order, figi, int(quantity), direction, account_id
        )

    async def get_orders(self, account_id: str) -> List[Dict[str, Any]]:
        return await self._rest_call(self._facade.get_orders, account_id)

    async def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        return await self._rest_call(self._facade.cancel_order, account_id, order_id)

    async def connect_websocket(self, user_id: int) -> bool:
        return await global_websocket_manager.ensure_connected(user_id, self._token, self.broker_type)

    async def subscribe_prices(
        self,
        user_id: int,
        figis: List[str],
        queue,
        candle_interval: Optional[str] = None,
    ) -> Dict[str, str]:
        return await global_websocket_manager.subscribe(
            user_id, self._token, self.broker_type, figis, queue, candle_interval=candle_interval
        )

    async def unsubscribe_prices(self, user_id: int, figis: List[str], queue) -> None:
        await global_websocket_manager.unsubscribe(user_id, self._token, self.broker_type, figis, queue)

    async def get_last_price(self, user_id: int, figi: str) -> Optional[float]:
        return await global_websocket_manager.get_last_price(user_id, self._token, self.broker_type, figi)

    async def close_websocket(self, user_id: int, queue=None) -> None:
        await global_websocket_manager.close(user_id, self._token, self.broker_type, queue=queue)

    async def force_resubscribe_websocket(self, user_id: int) -> bool:
        return await global_websocket_manager.force_resubscribe(
            user_id, self._token, self.broker_type
        )

    async def close(self) -> None:
        await self._facade.close()
