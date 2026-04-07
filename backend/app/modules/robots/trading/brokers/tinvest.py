from __future__ import annotations

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
    ) -> Dict[str, Any]:
        return await self._rest_call(self._facade.post_order, figi, quantity, price, direction, account_id)

    async def get_order_state(self, account_id: str, order_id: str) -> Dict[str, Any]:
        return await self._rest_call(self._facade.get_order_state, account_id, order_id)

    async def connect_websocket(self, user_id: int) -> bool:
        return await global_websocket_manager.ensure_connected(user_id, self._token, self.broker_type)

    async def subscribe_prices(self, user_id: int, figis: List[str], queue) -> Dict[str, str]:
        return await global_websocket_manager.subscribe(user_id, self._token, self.broker_type, figis, queue)

    async def unsubscribe_prices(self, user_id: int, figis: List[str], queue) -> None:
        await global_websocket_manager.unsubscribe(user_id, self._token, self.broker_type, figis, queue)

    async def get_last_price(self, user_id: int, figi: str) -> Optional[float]:
        return await global_websocket_manager.get_last_price(user_id, self._token, self.broker_type, figi)

    async def close_websocket(self, user_id: int, queue=None) -> None:
        await global_websocket_manager.close(user_id, self._token, self.broker_type, queue=queue)

    async def close(self) -> None:
        await self._facade.close()
