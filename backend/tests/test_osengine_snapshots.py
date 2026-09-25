"""Tests for OsEngine-backed daily universe snapshots."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from app.modules.osengine.snapshots import _rows_from_day_candles


def test_rows_from_day_candles_maps_ohlcv():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = [
        {
            "instrument_id": "SBER",
            "ticker": "SBER",
            "open": 100,
            "high": 110,
            "low": 95,
            "close": 105,
            "volume": 1000,
        }
    ]
    rows = _rows_from_day_candles(db, day=date(2024, 1, 15), board="TQBR", tickers=["SBER"])
    assert len(rows) == 1
    assert rows[0]["ticker"] == "SBER"
    assert rows[0]["last_price"] == 105.0
    assert rows[0]["open_price"] == 100.0
    assert rows[0]["value_today"] == 105.0 * 1000
    assert rows[0]["trading_status"] == "OsEngine"


def test_phase_label_snapshots_osengine():
    from app.modules.robots.backtest_progress import phase_label_ru

    assert phase_label_ru("prefetching_market_snapshots") == "OsEngine: снимки вселенной"
