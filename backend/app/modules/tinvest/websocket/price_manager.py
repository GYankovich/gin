"""
WebSocket менеджер для получения цен в реальном времени
"""
import asyncio
import websockets
import ssl
import json
from typing import Dict, List, Callable, Optional
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class PriceStreamManager:
    """Менеджер WebSocket для получения цен в реальном времени"""

    WS_URL = "wss://invest-public-api.tinkoff.ru/ws/tinkoff.public.invest.api.contract.v1.MarketDataStreamService/MarketDataStream"

    def __init__(self, token: str):
        self.token = token
        self.websocket = None
        self.connected = False

        # Подписки и колбэки
        self._subscribed_figis: set = set()
        self._callbacks: Dict[str, List[Callable]] = {}

        # Кэш последних цен
        self.last_prices: Dict[str, dict] = {}

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

    async def connect(self):
        """Подключается к WebSocket"""
        logger.info(f"Connecting to WebSocket...")

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        try:
            self.websocket = await websockets.connect(
                self.WS_URL,
                ssl=ssl_context,
                additional_headers={"Authorization": f"Bearer {self.token}"},
                subprotocols=["json"],
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            )
            self.connected = True
            logger.info("✅ WebSocket connected")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise

    async def subscribe(self, figis: List[str]) -> Dict[str, str]:
        """Подписывается на цены для указанных FIGI"""
        result = {}
        if not self.connected or not self.websocket:
            logger.warning("WebSocket is not connected, reconnecting before subscribe")
            await self.connect()

        new_figis = [f for f in figis if f not in self._subscribed_figis]
        if not new_figis:
            return {f: "ALREADY_SUBSCRIBED" for f in figis}

        instruments = [{"figi": figi, "instrumentId": figi} for figi in new_figis]
        subscribe_msg = {
            "subscribeLastPriceRequest": {
                "subscriptionAction": "SUBSCRIPTION_ACTION_SUBSCRIBE",
                "instruments": instruments
            }
        }

        logger.info(f"Subscribing to {len(new_figis)} FIGIs: {new_figis}")
        try:
            await self.websocket.send(json.dumps(subscribe_msg))
        except Exception as e:
            logger.warning(f"Subscribe send failed, reconnecting: {e}")
            self.connected = False
            await self.connect()
            await self.websocket.send(json.dumps(subscribe_msg))

        try:
            response = await asyncio.wait_for(self.websocket.recv(), timeout=10)
            response_data = json.loads(response)

            if "subscribeLastPriceResponse" in response_data:
                subs = response_data["subscribeLastPriceResponse"].get("lastPriceSubscriptions", [])
                for sub in subs:
                    figi = sub.get("figi")
                    status = sub.get("subscriptionStatus", "UNKNOWN")
                    result[figi] = status
                    if status == "SUBSCRIPTION_STATUS_SUCCESS":
                        self._subscribed_figis.add(figi)
                        logger.info(f"✅ Subscribed to {figi}")
                    else:
                        logger.warning(f"❌ Failed to subscribe to {figi}: {status}")

        except asyncio.TimeoutError:
            logger.error("Timeout waiting for subscription response")
            for figi in new_figis:
                result[figi] = "TIMEOUT"
        except Exception as e:
            logger.error(f"Error during subscription: {e}")
            for figi in new_figis:
                result[figi] = f"ERROR: {e}"

        return result

    def on_price(self, figi: str, callback: Callable):
        """Регистрирует колбэк на обновление цены"""
        if figi not in self._callbacks:
            self._callbacks[figi] = []
        self._callbacks[figi].append(callback)

    async def receive_once(self, timeout: float = 1.0) -> Optional[dict]:
        """
        Получает одно сообщение из WebSocket
        Returns:
            dict: полученное сообщение или None при таймауте/ошибке
        """
        if not self.connected or not self.websocket:
            # Avoid tight loops in callers (e.g. global fanout) starving the event loop.
            await asyncio.sleep(0.2)
            return None

        try:
            msg = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
            return json.loads(msg)
        except asyncio.TimeoutError:
            return None
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.connected = False
            return None
        except Exception as e:
            logger.error(f"Receive error: {e}")
            return None

    async def receive_prices(self, duration_seconds: float = 60.0) -> Dict[str, float]:
        """
        Получает цены в течение указанного времени
        Возвращает словарь {figi: last_price}
        """
        start_time = asyncio.get_event_loop().time()
        prices_received = {}

        while asyncio.get_event_loop().time() - start_time < duration_seconds:
            data = await self.receive_once(timeout=1.0)

            if data is None:
                continue

            if "lastPrice" in data:
                price_data = data["lastPrice"]
                figi = price_data.get("figi")
                price = self._parse_price(price_data.get("price"))

                if price is not None:
                    price_info = {
                        "figi": figi,
                        "price": price,
                        "time": price_data.get("time"),
                        "raw": price_data
                    }

                    self.last_prices[figi] = price_info
                    prices_received[figi] = price

                    for callback in self._callbacks.get(figi, []):
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(price_info)
                            else:
                                callback(price_info)
                        except Exception as e:
                            logger.error(f"Callback error for {figi}: {e}")

            elif "ping" in data:
                pong_msg = {"pong": data["ping"]}
                await self.websocket.send(json.dumps(pong_msg))

        return prices_received

    def get_last_price(self, figi: str) -> Optional[float]:
        """Возвращает последнюю известную цену"""
        info = self.last_prices.get(figi)
        return info["price"] if info else None

    async def close(self):
        """Закрывает соединение"""
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
        self.connected = False
        logger.info("WebSocket closed")