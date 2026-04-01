"""
Stage 2: Подключение к WebSocket и получение цен
Использует PriceParsingMixin для парсинга цен
"""
import asyncio
from typing import Dict, List, Optional

from app.modules.tinvest.websocket.price_manager import PriceStreamManager
from app.modules.robots.common.mixins import PriceParsingMixin
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Stage2WebSocket(PriceParsingMixin):
    """Подключение к WebSocket и получение цен"""
    _shared_managers: Dict[str, PriceStreamManager] = {}
    _shared_ref_counts: Dict[str, int] = {}
    _shared_lock = asyncio.Lock()

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

    async def connect(self) -> bool:
        """Подключается к WebSocket"""
        self._write_log("🔌 Подключение к WebSocket...")
        self._write_log(f"   Токен: {self.token[:10]}...{self.token[-10:]}")

        try:
            async with self._shared_lock:
                existing = self._shared_managers.get(self.token)
                if existing is None:
                    manager = PriceStreamManager(self.token)
                    await manager.connect()
                    self._shared_managers[self.token] = manager
                    self._shared_ref_counts[self.token] = 1
                    self.price_manager = manager
                    self._write_log("   ✅ WebSocket подключен (новое общее соединение)")
                else:
                    self.price_manager = existing
                    self._shared_ref_counts[self.token] = self._shared_ref_counts.get(self.token, 0) + 1
                    self._write_log("   ✅ Используется существующее общее WebSocket соединение")
            return True
        except Exception as e:
            self._write_log(f"   ❌ Ошибка подключения: {e}")
            return False

    async def subscribe(self, figis: List[str]) -> Dict[str, str]:
        """Подписывается на цены"""
        self._write_log(f"📡 Подписка на FIGIs: {figis}")

        if not self.price_manager:
            self._write_log("   ⚠️ Нет активного соединения, пробуем переподключиться...")
            connected = await self.connect()
            if not connected:
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
        """
        Получает цены в течение указанного времени
        Использует PriceParsingMixin.parse_price()
        """
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
                    # Используем метод из миксина
                    price = self.parse_price(price_data.get("price"))
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
        if not self.price_manager:
            return
        async with self._shared_lock:
            refs = max(0, self._shared_ref_counts.get(self.token, 0) - 1)
            self._shared_ref_counts[self.token] = refs
            if refs == 0:
                manager = self._shared_managers.pop(self.token, None)
                self._shared_ref_counts.pop(self.token, None)
                if manager:
                    await manager.close()
                self._write_log("   ✅ Общее WebSocket соединение закрыто")
            else:
                self._write_log(f"   ✅ Соединение оставлено активным (активных сессий: {refs})")
        self.price_manager = None