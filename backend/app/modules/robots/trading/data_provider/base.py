"""
Абстрактный DataProvider — общий интерфейс для backtest и live.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §4.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingDataProviderBase [1]
#/// Исходный модуль `backend/app/modules/robots/trading/data_provider/base.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import AsyncIterator, List, Optional, Tuple

from app.modules.robots.trading.contracts import Candle, MarketSnapshot


class DataProvider(ABC):
    """Общий контракт получения данных.

    Реализации:
    - `HistoricalDataProvider` — для бэктеста (читает БД).
    - `LiveDataProvider` — для реальной торговли (использует BrokerFacade).

    Не все методы обязательны: live-only методы (`subscribe_candles`) по умолчанию
    бросают `NotImplementedError` в исторической реализации, и наоборот.
    """

    @abstractmethod
    async def list_universe(self, trade_date: date) -> List[str]:
        """Полный список доступных тикеров на день D (TQBR справочник)."""

    @abstractmethod
    async def get_daily_summary(self, secids: List[str], trade_date: date) -> MarketSnapshot:
        """Снимок рынка на момент утра дня D (значения VALUE/NUMTRADES/OPEN/CLOSE и т.д.)."""

    @abstractmethod
    async def get_daily_candles(
        self,
        secid: str,
        from_d: date,
        to_d: date,
    ) -> List[Candle]:
        """Дневные свечи для ATR/lookback."""

    @abstractmethod
    async def get_intraday_candles(
        self,
        secid: str,
        day: date,
        interval: str,
    ) -> List[Candle]:
        """Внутридневные свечи по выбранному интервалу."""

    async def get_spread(self, secid: str, ts: datetime) -> Optional[Tuple[float, float]]:
        """Текущий bid/ask. Может вернуть None, если источник не предоставляет."""
        return None

    def subscribe_candles(self, secids: List[str], interval: str) -> AsyncIterator[Candle]:
        """Поток закрытых свечей (live-only)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} doesn't support streaming candles"
        )


__all__ = ["DataProvider"]
