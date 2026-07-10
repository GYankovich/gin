from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.robots import crypto_universe as cu


@pytest.fixture(autouse=True)
def _clear_tickers_cache():
    cu.clear_bybit_tickers_cache()
    yield
    cu.clear_bybit_tickers_cache()


def test_fetch_bybit_tickers_caches_second_call(monkeypatch):
    calls = {"n": 0}

    class _Client:
        def __init__(self, **kwargs):
            pass

        async def get_tickers(self, *, category: str, symbol=None):
            calls["n"] += 1
            return {"result": {"list": [{"symbol": "BTCUSDT", "lastPrice": "1"}]}}

        async def close(self):
            return None

    monkeypatch.setattr(cu, "BybitHttpClient", _Client)

    rows1 = asyncio.run(
        cu.fetch_bybit_tickers(
            api_key="k", api_secret="s", testnet=False, category="linear", ttl_seconds=60
        )
    )
    rows2 = asyncio.run(
        cu.fetch_bybit_tickers(
            api_key="k", api_secret="s", testnet=False, category="linear", ttl_seconds=60
        )
    )
    assert calls["n"] == 1
    assert rows1[0]["symbol"] == "BTCUSDT"
    assert rows2[0]["symbol"] == "BTCUSDT"
    # Mutating returned list must not poison cache
    rows2[0]["symbol"] = "HACK"
    rows3 = asyncio.run(
        cu.fetch_bybit_tickers(
            api_key="k", api_secret="s", testnet=False, category="linear", ttl_seconds=60
        )
    )
    assert rows3[0]["symbol"] == "BTCUSDT"


def test_fetch_bybit_tickers_force_bypasses_cache(monkeypatch):
    calls = {"n": 0}

    class _Client:
        def __init__(self, **kwargs):
            pass

        async def get_tickers(self, *, category: str, symbol=None):
            calls["n"] += 1
            return {"result": {"list": [{"symbol": f"S{calls['n']}"}]}}

        async def close(self):
            return None

    monkeypatch.setattr(cu, "BybitHttpClient", _Client)

    asyncio.run(
        cu.fetch_bybit_tickers(
            api_key="k", api_secret="s", testnet=False, category="linear", ttl_seconds=60
        )
    )
    rows = asyncio.run(
        cu.fetch_bybit_tickers(
            api_key="k",
            api_secret="s",
            testnet=False,
            category="linear",
            ttl_seconds=60,
            force=True,
        )
    )
    assert calls["n"] == 2
    assert rows[0]["symbol"] == "S2"
