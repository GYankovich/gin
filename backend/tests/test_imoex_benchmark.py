"""IMOEX benchmark: MOEX index market candles + DB persistence."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.market_data import service as market_service


def _moex_index_candles_payload(rows: list[tuple[str, float]]) -> dict:
    return {
        "candles": {
            "columns": ["open", "close", "high", "low", "value", "volume", "begin", "end"],
            "data": [
                [v, v, v, v, v, 0, begin, begin]
                for begin, v in rows
            ],
        }
    }


def test_fetch_moex_index_candles_uses_index_market_url():
    captured: dict = {}

    async def fake_moex(url, **kwargs):
        captured["url"] = url
        return _moex_index_candles_payload([
            ("2024-01-02 00:00:00", 100.0),
            ("2024-01-03 00:00:00", 102.0),
        ])

    async def _run():
        with patch.object(market_service, "_moex_get_json_with_retry", side_effect=fake_moex):
            return await market_service._fetch_moex_index_candles(
                "IMOEX",
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 10, tzinfo=timezone.utc),
            )

    rows = asyncio.run(_run())

    assert "/markets/index/securities/IMOEX/candles.json" in captured["url"]
    assert len(rows) == 2
    assert rows[0][0] == market_service.IMOEX_FIGI
    assert float(rows[0][6]) == 100.0
    assert float(rows[1][6]) == 102.0


def test_get_imoex_benchmark_builds_return_series():
    db = object()
    closes = [
        (datetime(2024, 1, 2, tzinfo=timezone.utc), 100.0),
        (datetime(2024, 1, 3, tzinfo=timezone.utc), 105.0),
    ]

    async def _run():
        with patch.object(market_service, "ensure_imoex_candles", new_callable=AsyncMock) as ensure_mock, patch.object(
            market_service, "run_in_threadpool", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)
        ), patch.object(market_service, "_load_imoex_closes", return_value=closes):
            result = await market_service.get_imoex_benchmark(
                db,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 10, tzinfo=timezone.utc),
            )
        ensure_mock.assert_awaited_once()
        return result

    result = asyncio.run(_run())
    assert result["unavailable"] is False
    assert result["return_percent"] == pytest.approx(5.0)
    assert len(result["series"]) == 2
    assert result["series"][0]["return_percent"] == pytest.approx(0.0)
    assert result["series"][1]["return_percent"] == pytest.approx(5.0)


def test_get_imoex_return_percent_uses_index_fetch_not_shares_board():
    async def _run():
        with patch.object(
            market_service,
            "_fetch_moex_index_candles",
            new_callable=AsyncMock,
            return_value=[
                (market_service.IMOEX_FIGI, market_service.IMOEX_DAY_INTERVAL,
                 datetime(2024, 1, 2, tzinfo=timezone.utc),
                 Decimal(100), Decimal(100), Decimal(100), Decimal(100), None),
                (market_service.IMOEX_FIGI, market_service.IMOEX_DAY_INTERVAL,
                 datetime(2024, 1, 3, tzinfo=timezone.utc),
                 Decimal(110), Decimal(110), Decimal(110), Decimal(110), None),
            ],
        ) as fetch_mock:
            pct = await market_service.get_imoex_return_percent(
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 10, tzinfo=timezone.utc),
            )
        fetch_mock.assert_awaited_once()
        return pct

    pct = asyncio.run(_run())
    assert pct == pytest.approx(10.0)
