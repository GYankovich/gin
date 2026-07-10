from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.modules.robots.trading.data.providers.db_cache import query_candles_cache_rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


def test_query_candles_cache_rows_uses_market_and_instrument_id():
    db = MagicMock()
    expected_rows = [{"candle_time": datetime(2024, 1, 1, tzinfo=timezone.utc), "close": 123.0}]
    db.execute.return_value = _FakeResult(expected_rows)

    out = query_candles_cache_rows(
        db,
        market="moex",
        instrument_id="SBER",
        ticker="IGNORED",
        interval_code="M5",
        interval_code_num=5,
        from_dt=datetime(2024, 1, 1, tzinfo=timezone.utc),
        to_dt_exclusive=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )

    assert out == expected_rows
    args, _ = db.execute.call_args
    params = args[1]
    assert params["market"] == "moex"
    assert params["instrument_id"] == "SBER"
    assert params["interval"] == "M5"
