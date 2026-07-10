#///EPIC MarketData.ITEM V1.TOPIC MoexTickerSharedCandles [1]
#/// Публичный контур ARCH-01: MOEX, TICKER, общая таблица shared_market_candles, фоновые jobs.

from app.modules.market_data_v1.router import router as market_data_v1_router

__all__ = ["market_data_v1_router"]
