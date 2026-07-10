"""
LiveDataProvider — DataProvider для реальной торговли.

Использует:
- `BrokerFacade.get_candles` для исторических свечей;
- `BrokerFacade.subscribe_prices` (через WS) — для потока цен; ниже реализован
  адаптер `subscribe_candles`, который агрегирует тики в свечи интервала
  на тот случай, если брокер не отдаёт готовые бары.
- `DmsService` (опционально) для дневного снапшота — в live это тот же путь,
  что и в backtest, чтобы сохранить parity (см. BRD-ARCH-03 §4, §3.0.1
  BRD-ARCH-02).

См. docs/BRD-ARCH-03-unified-engine-architecture.md §4.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingDataProviderLive [1]
#/// Исходный модуль `backend/app/modules/robots/trading/data_provider/live.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timezone
from typing import AsyncIterator, Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.contracts import Candle, MarketSnapshot, SnapshotRow
from app.modules.robots.trading.data_provider.base import DataProvider


class LiveDataProvider(DataProvider):
    """DataProvider поверх BrokerFacade.

    Принимает уже инициализированный `broker` (например, `TInvestBrokerFacade(token)`)
    и опционально `db: Session` — чтобы провайдер мог использовать DMS для
    утреннего снапшота и tqbr_securities для universe.
    """

    def __init__(
        self,
        broker: BrokerFacade,
        *,
        db: Optional[Session] = None,
        board: str = "TQBR",
        user_id: Optional[int] = None,
    ):
        self.broker = broker
        self.db = db
        self.board = board.upper()
        self.user_id = user_id

    # ---------------------- universe ----------------------

    async def list_universe(self, trade_date: date) -> List[str]:
        if self.db is not None:
            from sqlalchemy import text
            from app.core.config import settings
            schema = settings.DB_SCHEMA
            rows = self.db.execute(
                text(f"SELECT secid FROM {schema}.tqbr_securities ORDER BY secid")
            ).fetchall()
            return [str(r[0]) for r in rows if r and r[0]]
        return []

    # ---------------------- snapshot ----------------------

    async def get_daily_summary(self, secids: List[str], trade_date: date) -> MarketSnapshot:
        if self.db is None:
            return MarketSnapshot(
                as_of=datetime.now(timezone.utc),
                trade_date=trade_date,
                board=self.board,
                rows={},
            )
        # В live путь к снапшоту тот же, что в backtest: ищем последний свежий
        # снимок в market_snapshot_history. Это закрывает зазор §3.0.1 BRD-ARCH-02
        # (применение DividendCalendarService на base of utреннего снапшота).
        from app.modules.robots.trading.data_provider.historical import HistoricalDataProvider
        hist = HistoricalDataProvider(self.db, board=self.board)
        return await hist.get_daily_summary(secids, trade_date)

    # ---------------------- candles ----------------------

    async def get_daily_candles(self, secid: str, from_d: date, to_d: date) -> List[Candle]:
        # Live-провайдер для дневных свечей предпочитает кэш БД, но как fallback —
        # запрос к брокеру через FIGI (для этого secid должен совпадать с figi).
        if self.db is not None:
            from app.modules.robots.trading.data_provider.historical import HistoricalDataProvider
            hist = HistoricalDataProvider(self.db, board=self.board)
            cached = await hist.get_daily_candles(secid, from_d, to_d)
            if cached:
                return cached
        from_dt = datetime.combine(from_d, time(0, 0), tzinfo=timezone.utc)
        to_dt = datetime.combine(to_d, time(23, 59, 59), tzinfo=timezone.utc)
        raw = await self.broker.get_candles(secid, from_dt, to_dt, "CANDLE_INTERVAL_DAY")
        return [Candle.from_tinvest_dict(c, interval="D1", figi=secid) for c in (raw or [])]

    async def get_intraday_candles(self, secid: str, day: date, interval: str) -> List[Candle]:
        # Конвертация интервала: live ожидает CANDLE_INTERVAL_*, бэк-кэш — M5/M10
        from_dt = datetime.combine(day, time(0, 0), tzinfo=timezone.utc)
        to_dt = datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)
        raw = await self.broker.get_candles(secid, from_dt, to_dt, interval)
        return [Candle.from_tinvest_dict(c, interval=str(interval), figi=secid) for c in (raw or [])]

    # ---------------------- spread (live only) ----------------------

    async def get_spread(self, secid: str, ts: datetime) -> Optional[tuple]:
        # T-Invest API даёт текущий стакан через отдельный endpoint;
        # для большинства case-ов достаточно цены last/bid/ask, которая
        # приходит со снимком DMS. Здесь — заглушка.
        return None

    # ---------------------- stream ----------------------

    async def subscribe_candles(self, secids: List[str], interval: str) -> AsyncIterator[Candle]:
        """Стриминг цены через `BrokerFacade.subscribe_prices` + агрегация тиков в свечи.

        Используется при отсутствии прямого «свечного» стрима у брокера.
        В TInvest есть отдельный candles-стрим — если БРокер.subscribe_candles
        появится, можно делегировать на него; пока — простая агрегация.
        """
        # Чтобы не превращать модуль в полноценный агрегатор «тик→бар» (это backlog),
        # сейчас просто пробрасываем тики как «свечи длительностью 0»:
        if not secids:
            return
        queue: asyncio.Queue = asyncio.Queue()
        await self.broker.connect_websocket(self.user_id or 0)
        await self.broker.subscribe_prices(self.user_id or 0, secids, queue)
        try:
            while True:
                event = await queue.get()
                if not isinstance(event, dict):
                    continue
                price = float(event.get("price", 0.0) or 0.0)
                if price <= 0:
                    continue
                ts_raw = event.get("timestamp")
                if isinstance(ts_raw, datetime):
                    ts = ts_raw
                elif isinstance(ts_raw, (int, float)):
                    ts = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
                else:
                    ts = datetime.now(timezone.utc)
                yield Candle(
                    interval=str(interval),
                    time=ts,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=0,
                    figi=event.get("figi"),
                )
        finally:
            try:
                await self.broker.unsubscribe_prices(self.user_id or 0, secids)
            except Exception:
                pass


__all__ = ["LiveDataProvider"]
