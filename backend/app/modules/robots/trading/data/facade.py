"""
MarketDataFacade — единая точка доступа к свечам для backtest/live (BRD-ARCH-04 §4.1).

Этап 2: prefetch + gap-fill MOEX только через этот модуль; RobotsService не вызывает DMS/MOEX напрямую.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.modules.robots.trading.data.providers.db_cache import (
    query_candles_cache_rows,
    query_candles_cache_rows_bulk,
)
from app.modules.robots.trading.data.providers.moex_snapshots import ensure_daily_snapshot_history
from app.modules.robots.trading.data.providers.moex_backtest import (
    DEFAULT_PREFETCH_BATCH_SIZE,
    ensure_candles_moex_backtest,
    gap_fill_ticker_moex,
)
from app.modules.robots.trading.data.stats import CandlePrefetchStats, GapFillResult
from app.modules.robots.trading.intervals import ResolvedInterval

logger = logging.getLogger(__name__)

_default_facade: Optional["BacktestMoexMarketDataFacade"] = None


@runtime_checkable
class MarketDataFacade(Protocol):
    async def ensure_candles(
        self,
        db: Session,
        *,
        board: str,
        tickers: List[str],
        resolved: ResolvedInterval,
        from_date: date,
        till_date: date,
        user_id: Optional[int] = None,
        run_id: Optional[int] = None,
        batch_size: int = DEFAULT_PREFETCH_BATCH_SIZE,
        is_cancelled: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> CandlePrefetchStats: ...

    async def gap_fill_ticker(
        self,
        db: Session,
        *,
        board: str,
        ticker: str,
        interval_code: str,
        interval_code_num: int,
        from_day: date,
        to_day: date,
        user_id: Optional[int] = None,
    ) -> GapFillResult: ...

    def read_candles_cache_rows(
        self,
        db: Session,
        *,
        market: str = "moex",
        instrument_id: str | None = None,
        ticker: str,
        interval_code: str,
        interval_code_num: int,
        from_dt: datetime,
        to_dt_exclusive: datetime,
    ) -> List[Any]: ...

    def read_candles_cache_rows_bulk(
        self,
        db: Session,
        *,
        market: str = "moex",
        instrument_ids: List[str],
        interval_code: str,
        interval_code_num: int,
        from_dt: datetime,
        to_dt_exclusive: datetime,
        batch_size: int = 200,
    ) -> Dict[str, List[Any]]: ...

    async def ensure_snapshot_day(
        self,
        db: Session,
        *,
        day: date,
        board: str = "TQBR",
        user_id: Optional[int] = None,
        run_id: Optional[int] = None,
    ) -> Optional[int]: ...


class BacktestMoexMarketDataFacade:
    """DB-first свечи; MOEX ISS только через DmsService (providers/moex_backtest)."""

    async def ensure_candles(
        self,
        db: Session,
        *,
        board: str,
        tickers: List[str],
        resolved: ResolvedInterval,
        from_date: date,
        till_date: date,
        user_id: Optional[int] = None,
        run_id: Optional[int] = None,
        batch_size: int = DEFAULT_PREFETCH_BATCH_SIZE,
        is_cancelled: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> CandlePrefetchStats:
        return await ensure_candles_moex_backtest(
            db,
            board=board,
            tickers=tickers,
            resolved=resolved,
            from_date=from_date,
            till_date=till_date,
            user_id=user_id,
            run_id=run_id,
            batch_size=batch_size,
            is_cancelled=is_cancelled,
            progress_callback=progress_callback,
        )

    async def gap_fill_ticker(
        self,
        db: Session,
        *,
        board: str,
        ticker: str,
        interval_code: str,
        interval_code_num: int,
        from_day: date,
        to_day: date,
        user_id: Optional[int] = None,
    ) -> GapFillResult:
        return await gap_fill_ticker_moex(
            db,
            board=board,
            ticker=ticker,
            interval_code=interval_code,
            interval_code_num=interval_code_num,
            from_day=from_day,
            to_day=to_day,
            user_id=user_id,
        )

    def read_candles_cache_rows(
        self,
        db: Session,
        *,
        market: str = "moex",
        instrument_id: str | None = None,
        ticker: str,
        interval_code: str,
        interval_code_num: int,
        from_dt: datetime,
        to_dt_exclusive: datetime,
    ) -> List[Any]:
        return query_candles_cache_rows(
            db,
            market=market,
            instrument_id=instrument_id,
            ticker=ticker,
            interval_code=interval_code,
            interval_code_num=interval_code_num,
            from_dt=from_dt,
            to_dt_exclusive=to_dt_exclusive,
        )

    def read_candles_cache_rows_bulk(
        self,
        db: Session,
        *,
        market: str = "moex",
        instrument_ids: List[str],
        interval_code: str,
        interval_code_num: int,
        from_dt: datetime,
        to_dt_exclusive: datetime,
        batch_size: int = 200,
    ) -> Dict[str, List[Any]]:
        return query_candles_cache_rows_bulk(
            db,
            market=market,
            instrument_ids=instrument_ids,
            interval_code=interval_code,
            interval_code_num=interval_code_num,
            from_dt=from_dt,
            to_dt_exclusive=to_dt_exclusive,
            batch_size=batch_size,
        )

    async def ensure_snapshot_day(
        self,
        db: Session,
        *,
        day: date,
        board: str = "TQBR",
        user_id: Optional[int] = None,
        run_id: Optional[int] = None,
    ) -> Optional[int]:
        return await ensure_daily_snapshot_history(
            db,
            day=day,
            board=board,
            user_id=user_id,
            run_id=run_id,
        )


def get_market_data_facade() -> BacktestMoexMarketDataFacade:
    global _default_facade
    if _default_facade is None:
        _default_facade = BacktestMoexMarketDataFacade()
    return _default_facade


__all__ = [
    "BacktestMoexMarketDataFacade",
    "MarketDataFacade",
    "get_market_data_facade",
]
