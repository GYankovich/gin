from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.robots.crypto_universe import (
    CryptoUniverseFilters,
    ScreeningRow,
    _bulk_load_volatility_from_candles_cache,
    _volatility_from_ohlcv,
    enrich_volatility_metrics_live,
)


def test_volatility_from_ohlcv_basic():
    closes = [100 + i for i in range(20)]
    highs = [c + 2 for c in closes]
    lows = [c - 2 for c in closes]
    volumes = [1000.0] * 19 + [3000.0]
    rvol, atr = _volatility_from_ohlcv(highs, lows, closes, volumes, atr_period=14)
    assert rvol == pytest.approx(3.0)
    assert atr is not None and atr > 0


def test_bulk_load_volatility_from_candles_cache(monkeypatch):
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    bars = []
    for i in range(20):
        day = now.date() - timedelta(days=19 - i)
        close = 100.0 + i
        bars.append(
            {
                "instrument_id": "BTCUSDT",
                "candle_time": datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
                "open": close,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 1000.0 if i < 19 else 2500.0,
            }
        )

    monkeypatch.setattr(
        "app.modules.robots.trading.data.providers.db_cache.query_candles_cache_rows_bulk",
        lambda *a, **k: {"BTCUSDT": bars},
    )
    out = _bulk_load_volatility_from_candles_cache(
        db=MagicMock(),
        symbols=["BTCUSDT"],
        lookback_days=14,
        atr_period=14,
        now=now,
    )
    assert "BTCUSDT" in out
    rvol, atr = out["BTCUSDT"]
    assert rvol == pytest.approx(2.5)
    assert atr is not None


def test_enrich_volatility_uses_cache_skips_api(monkeypatch):
    monkeypatch.setattr(
        "app.modules.robots.crypto_universe._bulk_load_volatility_from_candles_cache",
        lambda *a, **k: {"ETHUSDT": (2.2, 3.5)},
    )
    client = MagicMock()
    client.get_kline = AsyncMock()
    db = MagicMock()
    row = ScreeningRow(symbol="ETHUSDT", turnover24h=1e8, lastPrice=3000.0, score=1.0)
    filters = CryptoUniverseFilters(min_rvol=1.5, min_atr_percent=1.0, max_atr_percent=15.0)
    stats = asyncio.run(
        enrich_volatility_metrics_live(client, [row], filters=filters, db=db)
    )
    assert stats["cache_hits"] == 1
    assert stats["api"] == 0
    assert stats["cache_commits"] == 0
    client.get_kline.assert_not_called()
    db.commit.assert_not_called()
    assert row.rvol == pytest.approx(2.2)
    assert row.atr_percent == pytest.approx(3.5)


def test_enrich_volatility_api_when_cache_incomplete(monkeypatch):
    # rvol missing but filter requires it → API
    monkeypatch.setattr(
        "app.modules.robots.crypto_universe._bulk_load_volatility_from_candles_cache",
        lambda *a, **k: {"SOLUSDT": (None, 4.0)},
    )
    upsert_calls: list[dict] = []

    def _fake_upsert(db, *, symbol, interval_label, rows):
        upsert_calls.append(
            {"symbol": symbol, "interval_label": interval_label, "rows": list(rows)}
        )
        return len(rows)

    monkeypatch.setattr(
        "app.modules.robots.trading.data.providers.bybit_market._upsert_bybit_candles",
        _fake_upsert,
    )
    client = MagicMock()
    client.get_kline = AsyncMock(
        return_value={
            "result": {
                "list": [
                    # ByBit order: newest first; code reverses for metrics
                    [str(1_700_000_000_000 + i * 86_400_000), "1", "3", "0.5", "2", str(100 + i)]
                    for i in range(20)
                ]
            }
        }
    )
    db = MagicMock()
    row = ScreeningRow(symbol="SOLUSDT", turnover24h=1e8, lastPrice=100.0, score=1.0)
    filters = CryptoUniverseFilters(min_rvol=1.5, min_atr_percent=1.0, atr_period=14, lookback_days=14)
    stats = asyncio.run(
        enrich_volatility_metrics_live(client, [row], filters=filters, db=db)
    )
    assert stats["api"] == 1
    assert stats["cache_hits"] == 0
    assert stats["kline_rows_written"] == 20
    assert stats["cache_commits"] == 1
    client.get_kline.assert_awaited()
    db.commit.assert_called()
    assert len(upsert_calls) == 1
    assert upsert_calls[0]["symbol"] == "SOLUSDT"
    assert upsert_calls[0]["interval_label"] == "D1"
    assert len(upsert_calls[0]["rows"]) == 20
