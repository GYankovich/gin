"""Tests for historical liquidity enrichment."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.modules.robots.trading.pipeline.historical_liquidity import (
    avg_daily_value_rub_from_candles,
    crypto_metrics_as_of_date,
)


def test_avg_daily_value_rub_from_candles(monkeypatch):
    def _fake_query(db, **kwargs):
        return [
            {"close": 100.0, "volume": 10.0},
            {"close": 110.0, "volume": 20.0},
        ]

    monkeypatch.setattr(
        "app.modules.robots.trading.pipeline.historical_liquidity.query_candles_cache_rows",
        _fake_query,
    )
    avg = avg_daily_value_rub_from_candles(
        SimpleNamespace(),
        ticker="SBER",
        as_of_date=date(2024, 6, 1),
        lookback_days=7,
    )
    assert avg == (1000.0 + 2200.0) / 2


def test_crypto_metrics_as_of_date(monkeypatch):
    def _fake_query(db, **kwargs):
        return [
            {
                "close": 50000.0,
                "volume": 100.0,
                "high": 51000.0,
                "low": 49000.0,
                "candle_time": datetime(2024, 1, 1, tzinfo=timezone.utc),
            }
        ]

    monkeypatch.setattr(
        "app.modules.robots.trading.pipeline.historical_liquidity.query_candles_cache_rows",
        _fake_query,
    )
    m = crypto_metrics_as_of_date(
        SimpleNamespace(),
        symbol="BTCUSDT",
        trade_date=date(2024, 1, 2),
        lookback_days=7,
    )
    assert m is not None
    assert m["symbol"] == "BTCUSDT"
    assert m["turnover24h"] == 5_000_000.0
    assert m["lastPrice"] == 50000.0
