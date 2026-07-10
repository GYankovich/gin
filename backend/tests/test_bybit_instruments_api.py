"""Tests for GET /bybit/instruments."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.modules.bybit.service import bybit_market_service


def test_list_instruments_normalizes_rows():
    from app.modules.bybit.instruments import list_instruments

    async def _run():
        with patch("app.modules.bybit.instruments.BybitHttpClient") as mock_cls:
            client = mock_cls.return_value
            client.get_instruments_info = AsyncMock(
                return_value={
                    "result": {
                        "list": [
                            {
                                "symbol": "BTCUSDT",
                                "baseCoin": "BTC",
                                "quoteCoin": "USDT",
                                "status": "Trading",
                            },
                            {"symbol": "DELISTED", "status": "Closed"},
                        ],
                        "nextPageCursor": None,
                    }
                }
            )
            rows = await list_instruments(category="linear", testnet=True)
            assert len(rows) == 1
            assert rows[0]["symbol"] == "BTCUSDT"

    asyncio.run(_run())


def test_get_instruments_service_response():
    async def _run():
        with patch(
            "app.modules.bybit.service.list_instruments",
            new=AsyncMock(
                return_value=[
                    {
                        "symbol": "ETHUSDT",
                        "base_coin": "ETH",
                        "quote_coin": "USDT",
                        "status": "Trading",
                        "category": "linear",
                    }
                ]
            ),
        ):
            res = await bybit_market_service.get_instruments(category="linear", testnet=True)
            assert res.total == 1
            assert res.items[0].symbol == "ETHUSDT"

    asyncio.run(_run())
