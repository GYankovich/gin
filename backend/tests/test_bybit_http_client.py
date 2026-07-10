from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import httpx
import pytest

from app.modules.bybit.http_client import BYBIT_API_MAINNET, BybitApiError, BybitHttpClient
from app.modules.bybit.signer import BybitSigner


def test_bybit_signer_signature_vector():
    signer = BybitSigner("demo_key", "demo_secret", recv_window=5000)
    ts = 1710000000000
    query = "accountType=UNIFIED"
    expected = hmac.new(
        b"demo_secret",
        f"{ts}demo_key5000{query}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert signer.sign(timestamp_ms=ts, query_string=query) == expected


def test_bybit_signer_canonical_body_sorted_compact():
    body = {"z": 2, "a": True, "none": None}
    assert BybitSigner.canonical_body(body) == json.dumps(
        {"a": True, "z": 2},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def test_bybit_client_uses_mainnet_base_url():
    c = BybitHttpClient(testnet=True)
    assert c.testnet is False
    assert c.base_url == BYBIT_API_MAINNET


def test_bybit_get_kline_public_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/market/kline"
        assert request.url.params["symbol"] == "BTCUSDT"
        return httpx.Response(
            200,
            json={"retCode": 0, "retMsg": "OK", "result": {"list": [["1", "2"]]}},
        )

    async def _run() -> dict:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = BybitHttpClient(testnet=True, http_client=http)
            return await client.get_kline(category="linear", symbol="BTCUSDT", interval="5")

    data = asyncio.run(_run())
    assert data["retCode"] == 0
    assert data["result"]["list"]


def test_bybit_get_tickers_public_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/market/tickers"
        assert request.url.params["category"] == "linear"
        return httpx.Response(
            200,
            json={"retCode": 0, "retMsg": "OK", "result": {"list": [{"symbol": "BTCUSDT"}]}},
        )

    async def _run() -> dict:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = BybitHttpClient(testnet=True, http_client=http)
            return await client.get_tickers(category="linear")

    data = asyncio.run(_run())
    assert data["retCode"] == 0
    assert data["result"]["list"][0]["symbol"] == "BTCUSDT"


def test_bybit_get_wallet_balance_private_requires_key_secret():
    async def _run() -> None:
        client = BybitHttpClient(testnet=True)
        with pytest.raises(BybitApiError):
            await client.get_wallet_balance(account_type="UNIFIED")

    asyncio.run(_run())


def test_bybit_signer_canonical_query_preserves_insertion_order():
    # Must match wire order — alphabetical sort caused retCode=10004 on transaction-log.
    q = BybitSigner.canonical_query(
        {
            "accountType": "UNIFIED",
            "startTime": 1783002352888,
            "endTime": 1783607152888,
            "limit": 50,
        }
    )
    assert q == (
        "accountType=UNIFIED&startTime=1783002352888&endTime=1783607152888&limit=50"
    )


def test_bybit_get_transaction_log_sign_matches_wire_query():
    signer = BybitSigner("k", "s", recv_window=5000)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/account/transaction-log"
        # Exact query we signed (no httpx reordering).
        wire_query = request.url.query.decode() if isinstance(request.url.query, (bytes, bytearray)) else str(request.url.query)
        assert wire_query == "accountType=UNIFIED&startTime=1000&endTime=2000&limit=50"
        ts = int(request.headers["X-BAPI-TIMESTAMP"])
        expected = signer.sign(
            timestamp_ms=ts,
            query_string=wire_query,
        )
        assert request.headers.get("X-BAPI-SIGN") == expected
        return httpx.Response(200, json={"retCode": 0, "retMsg": "OK", "result": {"list": []}})

    async def _run() -> dict:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = BybitHttpClient(
                testnet=True,
                api_key="k",
                api_secret="s",
                http_client=http,
            )
            return await client.get_transaction_log(
                account_type="UNIFIED",
                start_ms=1000,
                end_ms=2000,
                limit=50,
            )

    data = asyncio.run(_run())
    assert data["retCode"] == 0


def test_bybit_get_wallet_balance_private_headers():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/account/wallet-balance"
        assert request.headers.get("X-BAPI-API-KEY") == "k"
        assert request.headers.get("X-BAPI-SIGN")
        assert request.headers.get("X-BAPI-SIGN-TYPE") == "2"
        assert request.headers.get("Content-Type") == "application/json"
        return httpx.Response(200, json={"retCode": 0, "retMsg": "OK", "result": {"list": []}})

    async def _run() -> dict:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = BybitHttpClient(
                testnet=True,
                api_key="k",
                api_secret="s",
                http_client=http,
            )
            return await client.get_wallet_balance(account_type="UNIFIED")

    data = asyncio.run(_run())
    assert data["retCode"] == 0


def test_bybit_query_api_private_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/user/query-api"
        assert request.headers.get("X-BAPI-SIGN-TYPE") == "2"
        return httpx.Response(200, json={"retCode": 0, "retMsg": "OK", "result": {"apiKey": "k"}})

    async def _run() -> dict:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = BybitHttpClient(
                testnet=True,
                api_key="k",
                api_secret="s",
                http_client=http,
            )
            return await client.query_api()

    data = asyncio.run(_run())
    assert data["retCode"] == 0


def test_bybit_create_order_posts_signed_canonical_body():
  payload = {
      "category": "linear",
      "symbol": "BTCUSDT",
      "side": "Buy",
      "orderType": "Limit",
      "qty": "0.001",
      "price": "10000",
      "timeInForce": "GTC",
  }
  body_string = BybitSigner.canonical_body(payload)
  signer = BybitSigner("k", "s", recv_window=5000)

  def handler(request: httpx.Request) -> httpx.Response:
      assert request.url.path == "/v5/order/create"
      assert request.content == body_string.encode("utf-8")
      ts = int(request.headers["X-BAPI-TIMESTAMP"])
      expected = signer.sign(timestamp_ms=ts, body_string=body_string)
      assert request.headers.get("X-BAPI-SIGN") == expected
      return httpx.Response(200, json={"retCode": 0, "retMsg": "OK", "result": {"orderId": "oid-1"}})

  async def _run() -> dict:
      transport = httpx.MockTransport(handler)
      async with httpx.AsyncClient(transport=transport) as http:
          client = BybitHttpClient(
              testnet=True,
              api_key="k",
              api_secret="s",
              http_client=http,
          )
          return await client.create_order(
              category="linear",
              symbol="BTCUSDT",
              side="Buy",
              order_type="Limit",
              qty="0.001",
              price="10000",
              time_in_force="GTC",
          )

  data = asyncio.run(_run())
  assert data["result"]["orderId"] == "oid-1"


def test_bybit_retries_on_rate_limit_retcode_10006():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(
                200,
                json={"retCode": 10006, "retMsg": "Too many visits", "result": {}},
            )
        return httpx.Response(
            200,
            json={"retCode": 0, "retMsg": "OK", "result": {"list": []}},
        )

    async def _run() -> dict:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = BybitHttpClient(testnet=True, http_client=http)
            return await client.get_kline(category="linear", symbol="BTCUSDT", interval="D")

    data = asyncio.run(_run())
    assert data["retCode"] == 0
    assert calls["n"] == 3


def test_bybit_get_inter_transfer_list_and_funding_history_paths():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/v5/asset/transfer/query-inter-transfer-list":
            assert request.url.params.get("limit") == "50"
            return httpx.Response(
                200,
                json={"retCode": 0, "retMsg": "OK", "result": {"list": [], "nextPageCursor": ""}},
            )
        if request.url.path == "/v5/asset/fundinghistory":
            assert request.url.params.get("createTimeFrom") == "1700000000"
            assert request.url.params.get("createTimeTo") == "1700600000"
            return httpx.Response(
                200,
                json={"retCode": 0, "retMsg": "OK", "result": {"list": [], "nextPageCursor": ""}},
            )
        return httpx.Response(404, json={"retCode": 1, "retMsg": "unexpected"})

    async def _run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = BybitHttpClient(
                testnet=True,
                http_client=http,
                api_key="k",
                api_secret="s",
            )
            await client.get_inter_transfer_list(start_ms=1, end_ms=2, limit=50)
            await client.get_asset_funding_history(
                create_time_from_s=1700000000,
                create_time_to_s=1700600000,
                limit=100,
            )

    asyncio.run(_run())
    assert "/v5/asset/transfer/query-inter-transfer-list" in seen
    assert "/v5/asset/fundinghistory" in seen
