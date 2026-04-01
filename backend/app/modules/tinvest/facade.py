# app/modules/tinvest/facade.py

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import asyncio

from app.modules.tinvest.methods import create_tbank_client
from app.modules.tinvest.methods.instruments import InstrumentsClient
from app.modules.tinvest.websocket.price_manager import PriceStreamManager
from app.modules.robots.common.mixins import PriceParsingMixin
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class TInvestFacade(PriceParsingMixin):
    """Фасад для T-Invest API — чистая обёртка без дефолтных значений"""

    def __init__(self, token: str):
        self._token = token
        self._rest_client = None
        self._instruments_client = None
        self._ws_manager = None
        self._ws_connected = False

    @property
    def rest(self):
        if self._rest_client is None:
            self._rest_client = create_tbank_client(self._token)
        return self._rest_client

    @property
    def instruments(self):
        if self._instruments_client is None:
            self._instruments_client = InstrumentsClient(self._token)
        return self._instruments_client

    @property
    def websocket(self):
        if self._ws_manager is None:
            self._ws_manager = PriceStreamManager(self._token)
        return self._ws_manager

    # ============================================================
    # Управление счетами
    # ============================================================

    async def get_accounts(self) -> List[Dict[str, Any]]:
        """Получение списка счетов пользователя"""
        accounts = await self.rest.get_accounts()

        result = []
        for acc in accounts:
            result.append({
                "id": acc.get("id"),
                "type": self._normalize_account_type(acc.get("type", "")),
                "name": acc.get("name", ""),
                "status": self._normalize_account_status(acc.get("status", "")),
                "opened_date": acc.get("openedDate"),
                "closed_date": acc.get("closedDate"),
                "access_level": acc.get("accessLevel", "")
            })

        return result

    def _normalize_account_type(self, account_type: str) -> str:
        return account_type.replace("ACCOUNT_TYPE_", "") if account_type else ""

    def _normalize_account_status(self, status: str) -> str:
        return status.replace("ACCOUNT_STATUS_", "") if status else ""

    # ============================================================
    # Портфель и позиции
    # ============================================================

    async def get_portfolio(self, account_id: str) -> Dict[str, Any]:
        """Получение портфеля по счету"""
        portfolio = await self.rest.get_portfolio(account_id)

        return {
            "total_amount_portfolio": self.parse_money_value(portfolio.get("totalAmountPortfolio")),
            "total_amount_shares": self.parse_money_value(portfolio.get("totalAmountShares")),
            "total_amount_bonds": self.parse_money_value(portfolio.get("totalAmountBonds")),
            "total_amount_etf": self.parse_money_value(portfolio.get("totalAmountEtf")),
            "total_amount_currencies": self.parse_money_value(portfolio.get("totalAmountCurrencies")),
            "total_amount_futures": self.parse_money_value(portfolio.get("totalAmountFutures")),
            "total_amount_options": self.parse_money_value(portfolio.get("totalAmountOptions")),
            "expected_yield": self.parse_quotation(portfolio.get("expectedYield")),
            "daily_yield": self.parse_money_value(portfolio.get("dailyYield")),
            "daily_yield_relative": self.parse_quotation(portfolio.get("dailyYieldRelative")),
            "positions": [
                self._parse_position(pos)
                for pos in portfolio.get("positions", [])
            ]
        }

    def _parse_position(self, position: dict) -> dict:
        return {
            "figi": position.get("figi"),
            "ticker": position.get("ticker"),
            "instrument_type": position.get("instrumentType", ""),
            "quantity": self.parse_quotation(position.get("quantity")),
            "average_position_price": self.parse_money_value(position.get("averagePositionPrice")),
            "current_price": self.parse_money_value(position.get("currentPrice")),
            "expected_yield": self.parse_quotation(position.get("expectedYield")),
            "daily_yield": self.parse_money_value(position.get("dailyYield")),
            "blocked": position.get("blocked", False),
            "position_uid": position.get("positionUid"),
            "instrument_uid": position.get("instrumentUid")
        }

    async def get_portfolio_total_value(self, account_id: str) -> float:
        portfolio = await self.get_portfolio(account_id)
        total = portfolio.get("total_amount_portfolio", {})
        return total.get("decimal", 0.0) if total else 0.0

    async def get_free_funds(self, account_id: str) -> float:
        total = await self.get_portfolio_total_value(account_id)
        return total * 0.3  # временная заглушка

    # ============================================================
    # Свечи — БЕЗ ДЕФОЛТНЫХ ЗНАЧЕНИЙ
    # ============================================================

    async def get_candles(
            self,
            figi: str,
            from_date: datetime,
            to_date: datetime,
            interval: str  # ← без дефолта!
    ) -> List[Dict]:
        """
        Получение свечей по инструменту

        Args:
            figi: FIGI инструмента
            from_date: Начальная дата
            to_date: Конечная дата
            interval: Интервал свечей (обязательный параметр)

        Returns:
            Список свечей
        """
        return await self.instruments.get_candles(figi, from_date, to_date, interval)

    async def get_candles_with_logging(
            self,
            figi: str,
            from_date: datetime,
            to_date: datetime,
            interval: str,  # ← без дефолта!
            log_api_call_func=None,
            token_id: int = None,
            user_id: int = None
    ) -> List[Dict]:
        """
        Получение свечей с логированием API вызова

        Args:
            figi: FIGI инструмента
            from_date: Начальная дата
            to_date: Конечная дата
            interval: Интервал свечей (обязательный параметр)
            log_api_call_func: Функция для логирования
            token_id: ID токена для логирования
            user_id: ID пользователя для логирования
        """
        started_at = datetime.now(timezone.utc)
        endpoint = "tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles"
        request_data = {
            "figi": figi,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "interval": interval
        }

        try:
            candles = await self._call_with_retry(
                self.get_candles,
                figi,
                from_date,
                to_date,
                interval
            )

            if log_api_call_func:
                await log_api_call_func(
                    endpoint=endpoint,
                    request_data=request_data,
                    response_data={"candles_count": len(candles)},
                    response_status=200,
                    token_id=token_id,
                    user_id=user_id,
                    started_at=started_at
                )

            return candles

        except Exception as e:
            if log_api_call_func:
                await log_api_call_func(
                    endpoint=endpoint,
                    request_data=request_data,
                    error_message=str(e),
                    token_id=token_id,
                    user_id=user_id,
                    started_at=started_at
                )
            raise

    async def _call_with_retry(self, func, *args, max_attempts: int = 3, **kwargs):
        """
        Выполняет API вызов с ретраями при сетевых/транспортных ошибках.

        Args:
            func: Асинхронная функция API вызова.
            max_attempts: Количество попыток.

        Raises:
            Exception: Последнее исключение после исчерпания попыток.
        """
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                delay_seconds = 2 ** (attempt - 1)
                logger.warning(
                    "API call failed (attempt %s/%s): %s; retry in %ss",
                    attempt,
                    max_attempts,
                    exc,
                    delay_seconds
                )
                await asyncio.sleep(delay_seconds)
        raise last_error

    # ============================================================
    # Заявки (ордера)
    # ============================================================

    async def post_order(
            self,
            figi: str,
            quantity: int,
            price: float,
            direction: str,
            account_id: str
    ) -> Dict:
        """Выставление лимитной заявки"""
        return await self.instruments.post_order(figi, quantity, price, direction, account_id)

    async def get_order_state(self, account_id: str, order_id: str) -> Dict:
        """Получение статуса заявки"""
        return await self.instruments.get_order_state(account_id, order_id)

    # ============================================================
    # WebSocket для цен в реальном времени
    # ============================================================

    async def connect_websocket(self) -> bool:
        try:
            await self.websocket.connect()
            self._ws_connected = True
            return True
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            return False

    async def subscribe_prices(self, figis: List[str]) -> Dict[str, str]:
        if not self._ws_connected:
            await self.connect_websocket()
        return await self.websocket.subscribe(figis)

    async def get_prices(self, duration_seconds: int = 30) -> Dict[str, float]:
        if not self._ws_connected:
            await self.connect_websocket()
        return await self.websocket.receive_prices(duration_seconds)

    async def get_last_price(self, figi: str) -> Optional[float]:
        if self._ws_manager:
            return self._ws_manager.get_last_price(figi)
        return None

    async def close_websocket(self):
        if self._ws_manager:
            await self._ws_manager.close()
            self._ws_connected = False

    async def close(self):
        await self.close_websocket()