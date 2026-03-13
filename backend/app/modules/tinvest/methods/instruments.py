import httpx
import logging
import uuid
from typing import List, Dict, Optional
from datetime import datetime
from app.core.config import settings

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
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=data, headers=self.headers, timeout=30)
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"API error {response.status_code}: {error_text}")
                    raise Exception(f"API error: {error_text}")
                return response.json()
            except httpx.TimeoutException:
                raise Exception("Timeout connecting to T-Bank API")
            except Exception as e:
                logger.error(f"Request failed: {e}")
                raise

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
        data = {
            "figi": figi,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "interval": interval
        }
        result = await self._request(
            "tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles",
            data
        )
        return result.get("candles", [])

    async def post_order(self, figi: str, quantity: int, price: float, direction: str, account_id: str) -> Dict:
        """Выставить лимитную заявку"""
        # Преобразуем цену в units и nano
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

    async def get_accounts(self) -> List[Dict]:
        """Получить список счетов (используем существующий метод)"""
        from app.modules.tinvest.methods import create_tbank_client
        client = create_tbank_client(self.token)
        return await client.get_accounts()