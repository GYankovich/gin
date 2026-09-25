"""
Фоновый prefetch свечей в candles_cache перед фазой loading_candles history-backtest.

DEPRECATED: логика в `trading/data/`; этот модуль — тонкая обёртка для обратной совместимости.
TEMP: история только через OsEngine (MOEX/T-Invest ensure отключены).
"""

from __future__ import annotations

from datetime import date
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from app.modules.robots.trading.data import CandlePrefetchStats

# TEMP: MOEX ISS / MarketDataFacade history disabled — только OsEngine.
# from app.modules.robots.trading.data import get_market_data_facade
from app.modules.robots.trading.data.providers.moex_backtest import DEFAULT_PREFETCH_BATCH_SIZE
from app.modules.robots.trading.intervals import ResolvedInterval

__all__ = [
    "CandlePrefetchStats",
    "DEFAULT_PREFETCH_BATCH_SIZE",
    "prefetch_candles_for_backtest",
    "use_osengine_source",
]


def use_osengine_source(source: Optional[str]) -> bool:
    # TEMP: force OsEngine for all equity history prefetch.
    return True
    # src = (source or "").strip().lower()
    # if src == "osengine":
    #     return True
    # if src in ("moex", "tinvest", "bybit", "vtb", "alfa"):
    #     return False
    # return bool(settings.OSENGINE_ENABLED)


async def prefetch_candles_for_backtest(
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
    source: Optional[str] = None,
) -> CandlePrefetchStats:
    # TEMP: только OsEngine. Ниже — прежний MOEX/T-Invest путь (выключен).
    from app.modules.osengine import build_candle_ensure_request, get_osengine_facade

    facade = get_osengine_facade()
    req = build_candle_ensure_request(
        run_id=int(run_id or 0),
        tickers=tickers,
        interval=resolved.cache_label,
        from_date=from_date,
        till_date=till_date,
        board=board or "TQBR",
    )
    ose = await facade.ensure_candles_for_backtest(
        db,
        req,
        is_cancelled=is_cancelled,
        progress_callback=progress_callback,
    )
    return CandlePrefetchStats(
        total_tickers=ose.total_instruments,
        processed_tickers=ose.total_instruments if not ose.cancelled else ose.cache_full_hits + ose.instruments_with_gaps,
        cache_full_hits=ose.cache_full_hits,
        fetched_tickers=ose.instruments_with_gaps,
        fetched_ranges=ose.fetched_ranges,
        fetched_candles=ose.fetched_candles,
        cancelled=ose.cancelled,
        api_errors=ose.errors,
        last_api_error=ose.last_error,
        interval_label=resolved.cache_label,
        moex_interval_code=resolved.moex_interval_code,
    )

    # --- TEMP disabled: MOEX ISS / market_data facade history ---
    # return await get_market_data_facade().ensure_candles(
    #     db,
    #     board=board,
    #     tickers=tickers,
    #     resolved=resolved,
    #     from_date=from_date,
    #     till_date=till_date,
    #     user_id=user_id,
    #     run_id=run_id,
    #     batch_size=batch_size,
    #     is_cancelled=is_cancelled,
    #     progress_callback=progress_callback,
    # )
