"""Market data facade (BRD-ARCH-04 этап 2)."""

from .facade import BacktestMoexMarketDataFacade, MarketDataFacade, get_market_data_facade
from .stats import CandlePrefetchStats, GapFillResult

__all__ = [
    "BacktestMoexMarketDataFacade",
    "CandlePrefetchStats",
    "GapFillResult",
    "MarketDataFacade",
    "get_market_data_facade",
]
