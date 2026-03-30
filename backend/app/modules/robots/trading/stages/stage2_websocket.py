"""
Stage 2: Подключение к WebSocket и получение цен
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
import logging

from app.modules.tinvest.websocket.price_manager import PriceStreamManager

logger = logging.getLogger(__name__)


class Stage2WebSocket:
    """Подключение к WebSocket и получение цен"""

    WS_URL = "wss://invest-public-api.tinkoff.ru/ws/tinkoff.public.invest.api.contract.v1.MarketDataStreamService/MarketDataStream"

    def __init__(self, token: str, robot_id: int, log_func=None):
        self.token = token
        self.robot_id = robot_id
        self.log_func = log_func
        self.price_manager = None
        self.prices = {}

    def _write_log(self, message: str):
        """Запись в лог"""
        if self.log_func:
            self.log_func(f"[STAGE2] {message}")
        else:
            logger.info(f"[STAGE2] {message}")

    def _parse_price(self, price_data: dict) -> Optional[float]:
        """Безопасно парсит цену из units/nano"""
        if not price_data:
            return None

        units = price_data.get("units", 0)
        nano = price_data.get("nano", 0)

        try:
            units = int(units) if units else 0
        except (TypeError, ValueError):
            units = 0

        try:
            nano = int(nano) if nano else 0
        except (TypeError, ValueError):
            nano = 0

        return units + nano / 1e9

    async def connect(self) -> bool:
        """Подключается к WebSocket"""
        self._write_log("🔌 Подключение к WebSocket...")
        self._write_log(f"   URL: {self.WS_URL}")
        self._write_log(f"   Токен: {self.token[:10]}...{self.token[-10:]}")

        try:
            self.price_manager = PriceStreamManager(self.token)
            await self.price_manager.connect()
            self._write_log("   ✅ WebSocket подключен")
            return True
        except Exception as e:
            self._write_log(f"   ❌ Ошибка подключения: {e}")
            return False

    async def subscribe(self, figis: List[str]) -> Dict[str, str]:
        """Подписывается на цены"""
        self._write_log(f"📡 Подписка на FIGIs: {figis}")

        if not self.price_manager:
            self._write_log("   ❌ WebSocket не подключен")
            return {f: "NO_CONNECTION" for f in figis}

        try:
            result = await self.price_manager.subscribe(figis)
            for figi, status in result.items():
                self._write_log(f"   {figi}: {status}")
            return result
        except Exception as e:
            self._write_log(f"   ❌ Ошибка подписки: {e}")
            return {f: f"ERROR: {e}" for f in figis}

    async def receive_prices(self, duration_seconds: int = 30) -> Dict[str, float]:
        """Получает цены в течение указанного времени"""
        self._write_log(f"⏱️ Получение цен в течение {duration_seconds} секунд...")

        if not self.price_manager:
            self._write_log("   ❌ WebSocket не подключен")
            return {}

        try:
            start_time = asyncio.get_event_loop().time()
            prices = {}

            while asyncio.get_event_loop().time() - start_time < duration_seconds:
                # Используем receive_once из price_manager
                data = await self.price_manager.receive_once(timeout=1.0)

                if data and "lastPrice" in data:
                    price_data = data["lastPrice"]
                    figi = price_data.get("figi")
                    price = self._parse_price(price_data.get("price"))
                    if price is not None:
                        prices[figi] = price
                        self._write_log(f"   {figi}: {price:.4f} руб.")

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
        self._write_log("🔌 Закрытие WebSocket...")
        if self.price_manager:
            await self.price_manager.close()
            self._write_log("   ✅ WebSocket закрыт")