"""OsEngine candle prefetch — re-export from trading_core (canonical)."""

from __future__ import annotations

from app.modules.trading_core.data.osengine_prefetch import (
    DEFAULT_PREFETCH_BATCH_SIZE,
    CandlePrefetchStats,
    prefetch_candles_for_backtest,
    use_osengine_source,
)

__all__ = [
    "CandlePrefetchStats",
    "DEFAULT_PREFETCH_BATCH_SIZE",
    "prefetch_candles_for_backtest",
    "use_osengine_source",
]
