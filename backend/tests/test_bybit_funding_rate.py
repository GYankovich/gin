from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx

from app.modules.bybit.funding import clear_funding_rate_cache, fetch_funding_rate
from app.modules.bybit.http_client import BybitHttpClient


class _FakeTickersClient:
    async def get_tickers(self, *, category: str, symbol: str | None = None):
        assert category == "linear"
        assert symbol == "BTCUSDT"
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "fundingRate": "0.00015",
                        "nextFundingTime": "1704067200000",
                    }
                ]
            },
        }

    async def close(self):
        return None


def test_fetch_funding_rate_linear():
    clear_funding_rate_cache()

    async def _run():
        return await fetch_funding_rate(
            symbol="btcusdt",
            instrument_category="linear",
            testnet=True,
            client=_FakeTickersClient(),
        )

    row = asyncio.run(_run())
    assert row.symbol == "BTCUSDT"
    assert row.funding_rate == 0.00015
    assert row.next_funding_time == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert row.testnet is True


def test_fetch_funding_rate_spot_returns_zero():
    clear_funding_rate_cache()

    async def _run():
        return await fetch_funding_rate(
            symbol="BTCUSDT",
            instrument_category="spot",
            testnet=True,
            client=_FakeTickersClient(),
        )

    row = asyncio.run(_run())
    assert row.instrument_category == "spot"
    assert row.funding_rate == 0.0
    assert row.next_funding_time is None


def test_fetch_funding_rate_uses_cache():
    clear_funding_rate_cache()
    client = _FakeTickersClient()
    client.get_tickers = AsyncMock(side_effect=client.get_tickers)

    async def _run():
        first = await fetch_funding_rate(
            symbol="BTCUSDT",
            instrument_category="linear",
            testnet=True,
            client=client,
        )
        second = await fetch_funding_rate(
            symbol="BTCUSDT",
            instrument_category="linear",
            testnet=True,
            client=client,
        )
        return first, second

    first, second = asyncio.run(_run())
    assert first.funding_rate == second.funding_rate
    assert client.get_tickers.await_count == 1


def test_fetch_funding_rate_integration_mock_transport():
    clear_funding_rate_cache()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/market/tickers"
        return httpx.Response(
            200,
            json={
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "symbol": "ETHUSDT",
                            "fundingRate": "0.0002",
                            "nextFundingTime": "1704153600000",
                        }
                    ]
                },
            },
        )

    async def _run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = BybitHttpClient(testnet=True, http_client=http)
            return await fetch_funding_rate(
                symbol="ETHUSDT",
                instrument_category="linear",
                testnet=True,
                client=client,
            )

    row = asyncio.run(_run())
    assert row.symbol == "ETHUSDT"
    assert row.funding_rate == 0.0002
