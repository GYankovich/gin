"""
Stage 2: Подключение к WebSocket и получение цен
Использует PriceParsingMixin для парсинга цен
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingStagesStage2Websocket [1]
#/// Исходный модуль `backend/app/modules/robots/trading/stages/stage2_websocket.py` — автоматическая разметка для Obsidian Source Scanner.

import asyncio
from typing import Dict, List, Optional

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.common.mixins import PriceParsingMixin
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Stage2WebSocket(PriceParsingMixin):
    """Подключение к WebSocket и получение цен"""
    def __init__(self, broker: BrokerFacade, user_id: int, robot_id: int, broker_type: str = "tinvest", log_func=None):
        self.broker = broker
        self.user_id = user_id
        self.robot_id = robot_id
        self.broker_type = broker_type
        self.log_func = log_func
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribed_figis = set()
        self.prices = {}

    def _write_log(self, message: str):
        """Запись в лог"""
        if self.log_func:
            self.log_func(f"[STAGE2] {message}")
        else:
            logger.info(f"[STAGE2] {message}")

    async def connect(self) -> bool:
        """Подключается к WebSocket"""
        self._write_log("🔌 Подключение к глобальному WebSocket...")
        return await self.broker.connect_websocket(self.user_id)

    async def subscribe(self, figis: List[str], candle_interval: Optional[str] = None) -> Dict[str, str]:
        """Подписывается на last price и (опционально) поток свечей."""
        self._write_log(f"📡 Подписка на FIGIs: {figis}")
        if candle_interval:
            self._write_log(f"   Candle stream interval: {candle_interval}")

        try:
            result = await self.broker.subscribe_prices(
                self.user_id, figis, self._queue, candle_interval=candle_interval
            )
            self._subscribed_figis.update(figis)
            for figi, status in result.items():
                self._write_log(f"   {figi}: {status}")
            return result
        except Exception as e:
            self._write_log(f"   ❌ Ошибка подписки: {e}")
            return {f: f"ERROR: {e}" for f in figis}

    async def receive_events(self, duration_seconds: int = 30) -> List[Dict]:
        """Читает события из очереди: price и candle_closed."""
        self._write_log(f"⏱️ Ожидание market events {duration_seconds} сек...")
        start_time = asyncio.get_event_loop().time()
        events: List[Dict] = []

        while asyncio.get_event_loop().time() - start_time < duration_seconds:
            try:
                data = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if not data or not isinstance(data, dict):
                continue

            ev_type = data.get("type")
            if ev_type in ("price", "candle"):
                # "candle" = ByBit in-progress kline update (legacy); treat as price tick.
                figi = data.get("figi")
                price = data.get("price")
                if price is None and ev_type == "candle":
                    candle = data.get("candle") or {}
                    if candle.get("close") is not None:
                        price = self.parse_price(candle.get("close"))
                if figi and price is not None:
                    self.prices[figi] = float(price)
                    # Normalize for downstream counters / session.
                    events.append({"type": "price", "figi": figi, "price": float(price)})
            elif ev_type == "candle_closed":
                figi = data.get("figi")
                candle = data.get("candle") or {}
                price = data.get("price")
                if price is None and candle.get("close") is not None:
                    price = self.parse_price(candle.get("close"))
                if figi and price is not None:
                    self.prices[figi] = float(price)
                events.append(data)
                self._write_log(
                    f"   🕯️ Closed candle {figi} @ {float(price or 0):.4f} time={candle.get('time')}"
                )

        prices_count = sum(1 for e in events if e.get("type") == "price")
        candles_count = sum(1 for e in events if e.get("type") == "candle_closed")
        self._write_log(
            f"📊 Events: prices={prices_count}, candles_closed={candles_count}, "
            f"cached_symbols={len(self.prices)}"
        )
        return events

    async def receive_prices(self, duration_seconds: int = 30) -> Dict[str, float]:
        """
        Получает цены в течение указанного времени
        Использует PriceParsingMixin.parse_price()
        """
        self._write_log(f"⏱️ Получение цен в течение {duration_seconds} секунд...")

        try:
            start_time = asyncio.get_event_loop().time()
            prices = {}

            while asyncio.get_event_loop().time() - start_time < duration_seconds:
                try:
                    data = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if data and data.get("type") == "price":
                    figi = data.get("figi")
                    price = data.get("price")
                    if figi and price is not None:
                        prices[figi] = float(price)
                        self.prices[figi] = float(price)
                        self._write_log(f"   {figi}: {float(price):.4f} руб.")

            self._write_log(f"📊 Получено цен: {len(prices)}")
            return prices

        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения цен: {e}")
            return {}

    def get_last_price(self, figi: str) -> Optional[float]:
        """Возвращает последнюю цену"""
        return self.prices.get(figi)

    async def close(self):
        """Закрывает WebSocket"""
        self._write_log("🔌 Отписка от WebSocket (соединение сохраняется)...")
        try:
            if self._subscribed_figis:
                await self.broker.unsubscribe_prices(self.user_id, list(self._subscribed_figis), self._queue)
            self._subscribed_figis.clear()
        except Exception as e:
            self._write_log(f"   ❌ Ошибка закрытия WebSocket: {e}")