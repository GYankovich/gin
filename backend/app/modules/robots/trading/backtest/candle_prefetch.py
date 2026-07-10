"""
Фоновый prefetch свечей в candles_cache перед фазой loading_candles history-backtest.

DEPRECATED: логика в `trading/data/`; этот модуль — тонкая обёртка для обратной совместимости.
"""

from __future__ import annotations

from datetime import date
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from app.modules.robots.trading.data import CandlePrefetchStats, get_market_data_facade
from app.modules.robots.trading.data.providers.moex_backtest import DEFAULT_PREFETCH_BATCH_SIZE
from app.modules.robots.trading.intervals import ResolvedInterval

__all__ = [
    "CandlePrefetchStats",
    "DEFAULT_PREFETCH_BATCH_SIZE",
    "prefetch_candles_for_backtest",
]


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
) -> CandlePrefetchStats:
    return await get_market_data_facade().ensure_candles(
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
