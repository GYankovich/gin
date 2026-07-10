"""MarketDataFacade — этап 2 BRD-ARCH-04."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.robots.trading.data import (
    BacktestMoexMarketDataFacade,
    CandlePrefetchStats,
    get_market_data_facade,
)
from app.modules.robots.trading.intervals import resolve_strategy_interval


def test_get_market_data_facade_singleton():
    a = get_market_data_facade()
    b = get_market_data_facade()
    assert a is b
    assert isinstance(a, BacktestMoexMarketDataFacade)


def test_candle_prefetch_stats_unsupported_summary():
    s = CandlePrefetchStats(skipped_unsupported_interval=True, moex_interval_code=99)
    assert "not supported" in s.summary()


def test_ensure_candles_empty_tickers():
    import asyncio

    db = MagicMock()
    resolved = resolve_strategy_interval({"interval": "M5"})
    facade = BacktestMoexMarketDataFacade()

    stats = asyncio.run(
        facade.ensure_candles(
            db,
            board="TQBR",
            tickers=[],
            resolved=resolved,
            from_date=date(2024, 1, 1),
            till_date=date(2024, 1, 31),
        )
    )
    assert stats.total_tickers == 0
    assert stats.processed_tickers == 0


def test_ensure_candles_delegates_to_provider():
    import asyncio

    db = MagicMock()
    resolved = resolve_strategy_interval({"interval": "M5"})
    expected = CandlePrefetchStats(total_tickers=2, processed_tickers=2)
    facade = BacktestMoexMarketDataFacade()

    with patch(
        "app.modules.robots.trading.data.facade.ensure_candles_moex_backtest",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_ensure:
        stats = asyncio.run(
            facade.ensure_candles(
                db,
                board="TQBR",
                tickers=["SBER", "GAZP"],
                resolved=resolved,
                from_date=date(2024, 1, 1),
                till_date=date(2024, 1, 31),
            )
        )
    mock_ensure.assert_awaited_once()
    assert stats is expected


def test_read_candles_cache_rows_delegates_market_key():
    from datetime import datetime, timezone

    db = MagicMock()
    facade = BacktestMoexMarketDataFacade()
    expected = [{"candle_time": datetime(2024, 1, 1, tzinfo=timezone.utc), "close": 1.0}]
    from_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2024, 1, 2, tzinfo=timezone.utc)

    with patch(
        "app.modules.robots.trading.data.facade.query_candles_cache_rows",
        return_value=expected,
    ) as mock_query:
        got = facade.read_candles_cache_rows(
            db,
            market="moex",
            instrument_id="SBER",
            ticker="SBER",
            interval_code="M5",
            interval_code_num=5,
            from_dt=from_dt,
            to_dt_exclusive=to_dt,
        )
    mock_query.assert_called_once_with(
        db,
        market="moex",
        instrument_id="SBER",
        ticker="SBER",
        interval_code="M5",
        interval_code_num=5,
        from_dt=from_dt,
        to_dt_exclusive=to_dt,
    )
    assert got == expected


def test_read_candles_cache_rows_bulk_delegates():
    from datetime import datetime, timezone

    db = MagicMock()
    facade = BacktestMoexMarketDataFacade()
    expected = {"SBER": [{"close": 1.0}]}
    from_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2024, 1, 2, tzinfo=timezone.utc)

    with patch(
        "app.modules.robots.trading.data.facade.query_candles_cache_rows_bulk",
        return_value=expected,
    ) as mock_bulk:
        got = facade.read_candles_cache_rows_bulk(
            db,
            market="bybit",
            instrument_ids=["SBER", "GAZP"],
            interval_code="M5",
            interval_code_num=5,
            from_dt=from_dt,
            to_dt_exclusive=to_dt,
            batch_size=40,
        )
    mock_bulk.assert_called_once_with(
        db,
        market="bybit",
        instrument_ids=["SBER", "GAZP"],
        interval_code="M5",
        interval_code_num=5,
        from_dt=from_dt,
        to_dt_exclusive=to_dt,
        batch_size=40,
    )
    assert got == expected
