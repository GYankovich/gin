"""Bulk candles_cache reads."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.modules.robots.trading.data.providers.db_cache import (
    query_candles_cache_rows,
    query_candles_cache_rows_bulk,
)


def _row(iid: str, minute: int, close: float = 100.0):
    return {
        "instrument_id": iid,
        "candle_time": datetime(2024, 6, 1, 10, minute, tzinfo=timezone.utc),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1,
    }


def test_query_candles_cache_rows_bulk_groups_by_instrument():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.side_effect = [
        [_row("SBER", 0), _row("GAZP", 0)],
        [],
    ]

    from_dt = datetime(2024, 6, 1, tzinfo=timezone.utc)
    to_dt = datetime(2024, 6, 2, tzinfo=timezone.utc)
    got = query_candles_cache_rows_bulk(
        db,
        market="moex",
        instrument_ids=["SBER", "GAZP"],
        interval_code="M5",
        interval_code_num=5,
        from_dt=from_dt,
        to_dt_exclusive=to_dt,
        batch_size=200,
    )

    assert set(got.keys()) == {"SBER", "GAZP"}
    assert len(got["SBER"]) == 1
    assert len(got["GAZP"]) == 1
    assert db.execute.call_count == 1
    first_sql = str(db.execute.call_args_list[0][0][0])
    assert "instrument_id = ANY" in first_sql


def test_query_candles_cache_rows_delegates_to_bulk():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = [_row("BTCUSDT", 5, 42.0)]

    from_dt = datetime(2024, 6, 1, tzinfo=timezone.utc)
    to_dt = datetime(2024, 6, 2, tzinfo=timezone.utc)
    rows = query_candles_cache_rows(
        db,
        market="bybit",
        instrument_id="BTCUSDT",
        ticker="BTCUSDT",
        interval_code="M5",
        interval_code_num=5,
        from_dt=from_dt,
        to_dt_exclusive=to_dt,
    )

    assert len(rows) == 1
    assert rows[0]["close"] == 42.0


def test_load_candles_by_symbol_from_cache_uses_bulk():
    from datetime import date, time, timedelta

    from app.modules.robots.trading.runtime.orchestrator import TradingOrchestrator

    db = MagicMock()
    from_dt = datetime.combine(date(2024, 6, 1), time.min, tzinfo=timezone.utc)
    to_dt = from_dt + timedelta(days=1)
    bulk = {
        "BTCUSDT": [
            {
                "candle_time": datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 10,
            }
        ]
    }

    facade = MagicMock()
    facade.read_candles_cache_rows_bulk.return_value = bulk

    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "app.modules.robots.trading.data.get_market_data_facade",
        return_value=facade,
    ):
        out = TradingOrchestrator().load_candles_by_symbol_from_cache(
            db,
            symbols=["BTCUSDT"],
            interval_code="M5",
            interval_code_num=5,
            from_dt=from_dt,
            to_dt_exclusive=to_dt,
            market="bybit",
        )

    facade.read_candles_cache_rows_bulk.assert_called_once()
    assert "BTCUSDT" in out
    assert out["BTCUSDT"][0]["close"]["units"] == 1
