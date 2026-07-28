#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesTinvestMethodsInstruments [1]
#/// Исходный модуль `backend/app/modules/tinvest/methods/instruments.py` — автоматическая разметка для Obsidian Source Scanner.

import logging
import uuid
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta

from app.modules.tinvest.http_client import post_with_transport_recovery
logger = logging.getLogger(__name__)


class InstrumentsClient:
    """Клиент для получения данных об инструментах и выставления заявок"""
    BASE_URL = "https://invest-public-api.tbank.ru/rest"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _request(self, endpoint: str, data: dict = None) -> dict:
        """Базовый POST-запрос к API Т-Банка"""
        url = f"{self.BASE_URL}/{endpoint}"
        try:
            response = await post_with_transport_recovery(
                url,
                headers=self.headers,
                json=data,
                timeout=30.0,
                token=self.token,
            )
        except Exception as e:
            raise Exception(f"Network error connecting to T-Bank API: {e}") from e
        if response.status_code != 200:
            error_text = (response.text or "").strip()
            if not error_text:
                try:
                    error_text = str(response.json())
                except Exception:
                    error_text = f"<empty body>, status={response.status_code}"
            logger.error("T-Bank API error %s: %s", response.status_code, error_text)
            raise Exception(f"API error [{response.status_code}]: {error_text}")
        return response.json()

    async def get_shares(self) -> List[Dict]:
        """Получить список акций"""
        result = await self._request(
            "tinkoff.public.invest.api.contract.v1.InstrumentsService/Shares",
            {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}
        )
        return result.get("instruments", [])

    async def get_etfs(self) -> List[Dict]:
        """Получить список ETF"""
        result = await self._request(
            "tinkoff.public.invest.api.contract.v1.InstrumentsService/Etfs",
            {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}
        )
        return result.get("instruments", [])

    async def get_bonds(self) -> List[Dict]:
        """Получить список облигаций"""
        result = await self._request(
            "tinkoff.public.invest.api.contract.v1.InstrumentsService/Bonds",
            {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}
        )
        return result.get("instruments", [])

    async def get_candles(self, figi: str, from_date: datetime, to_date: datetime, interval: str = "CANDLE_INTERVAL_DAY") -> List[Dict]:
        """Получить свечи по инструменту"""
        from_u = self._as_utc(from_date)
        to_u = self._as_utc(to_date)
        if from_u >= to_u:
            return []
        return await self._get_candles_chunked(figi, from_u, to_u, interval)

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    async def _get_candles_once(self, figi: str, from_date: datetime, to_date: datetime, interval: str) -> List[Dict]:
        from_str = from_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        to_str = to_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        data = {
            "figi": figi,
            "from": from_str,
            "to": to_str,
            "interval": interval,
        }
        logger.debug("Requesting candles for %s from %s to %s", figi, from_str, to_str)
        result = await self._request(
            "tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles",
            data,
        )
        return result.get("candles", [])

    @staticmethod
    def _is_range_too_large_error(error: Exception) -> bool:
        message = str(error).lower()
        return ("30014" in message) or ("maximum request period" in message)

    @staticmethod
    def _is_bad_request_error(error: Exception) -> bool:
        return '"code":4' in str(error).replace(" ", "").lower()

    async def _get_candles_chunked(
        self,
        figi: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        depth: int = 0,
    ) -> List[Dict]:
        """
        Для ошибки 30014 (слишком большой период) автоматически дробит диапазон.
        """
        if depth > 24:
            logger.warning(
                "Candle chunk recursion depth exceeded for figi=%s interval=%s range=%s..%s",
                figi, interval, from_date.isoformat(), to_date.isoformat(),
            )
            return []
        try:
            return await self._get_candles_once(figi, from_date, to_date, interval)
        except Exception as e:
            is_too_large = self._is_range_too_large_error(e)
            is_bad_request = self._is_bad_request_error(e)
            if not is_too_large and not is_bad_request:
                raise
            if (to_date - from_date) <= timedelta(minutes=1):
                if is_bad_request:
                    logger.warning(
                        "Skipping tiny bad candle chunk figi=%s interval=%s range=%s..%s error=%s",
                        figi, interval, from_date.isoformat(), to_date.isoformat(), e,
                    )
                    return []
                raise

            middle = from_date + (to_date - from_date) / 2
            if middle <= from_date or middle >= to_date:
                if is_bad_request:
                    logger.warning(
                        "Skipping invalid candle chunk split figi=%s interval=%s range=%s..%s error=%s",
                        figi, interval, from_date.isoformat(), to_date.isoformat(), e,
                    )
                    return []
                raise

            left = await self._get_candles_chunked(figi, from_date, middle, interval, depth + 1)
            right = await self._get_candles_chunked(figi, middle, to_date, interval, depth + 1)
            merged = left + right

            # На границе диапазонов свеча может повториться — убираем дубли по времени.
            dedup: Dict[str, Dict] = {}
            for candle in merged:
                key = str(candle.get("time") or "")
                if key:
                    dedup[key] = candle
            if dedup:
                return [dedup[k] for k in sorted(dedup.keys())]
            return merged

    async def post_order(self, figi: str, quantity: int, price: float, direction: str, account_id: str) -> Dict:
        """Выставить лимитную заявку"""
        units = int(price)
        nano = int((price - units) * 1_000_000_000)
        data = {
            "figi": figi,
            "quantity": quantity,
            "price": {"units": units, "nano": nano},
            "direction": direction,  # "ORDER_DIRECTION_BUY" или "ORDER_DIRECTION_SELL"
            "accountId": account_id,
            "orderType": "ORDER_TYPE_LIMIT",
            "orderId": str(uuid.uuid4())
        }
        return await self._request(
            "tinkoff.public.invest.api.contract.v1.OrdersService/PostOrder",
            data
        )

    async def post_market_order(
        self,
        figi: str,
        quantity: int,
        direction: str,
        account_id: str,
    ) -> Dict:
        """Рыночная заявка (без цены)."""
        data = {
            "figi": figi,
            "quantity": int(quantity),
            "direction": direction,
            "accountId": account_id,
            "orderType": "ORDER_TYPE_MARKET",
            "orderId": str(uuid.uuid4()),
        }
        return await self._request(
            "tinkoff.public.invest.api.contract.v1.OrdersService/PostOrder",
            data,
        )

    async def get_orders(self, account_id: str) -> List[Dict]:
        """Активные и недавние заявки по счёту."""
        result = await self._request(
            "tinkoff.public.invest.api.contract.v1.OrdersService/GetOrders",
            {"accountId": account_id},
        )
        return result.get("orders", [])

    async def cancel_order(self, account_id: str, order_id: str) -> Dict:
        """Отмена заявки."""
        return await self._request(
            "tinkoff.public.invest.api.contract.v1.OrdersService/CancelOrder",
            {"accountId": account_id, "orderId": order_id},
        )

    async def get_accounts(self) -> List[Dict]:
        """Получить список счетов (используем существующий метод)"""
        from app.modules.tinvest.methods import create_tbank_client
        client = create_tbank_client(self.token)
        return await client.get_accounts()

    async def get_order_state(self, account_id: str, order_id: str) -> Dict:
        """
        Получает статус заявки

        Args:
            account_id: ID счета
            order_id: ID заявки

        Returns:
            Dict: статус заявки
        """
        data = {
            "accountId": account_id,
            "orderId": order_id
        }
        return await self._request(
            "tinkoff.public.invest.api.contract.v1.OrdersService/GetOrderState",
            data
        )