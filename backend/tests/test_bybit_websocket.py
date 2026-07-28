from __future__ import annotations

import asyncio
import json

from app.modules.bybit.websocket import (
    BYBIT_WS_PUBLIC_MAINNET,
    BybitWebSocketClient,
    kline_topic,
    parse_kline_event,
    symbol_from_kline_topic,
)


class _FakeWS:
    def __init__(self, recv_queue: list[str] | None = None) -> None:
        self.sent: list[str] = []
        self.closed = False
        self._queue = list(recv_queue or [])

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def recv(self) -> str:
        if not self._queue:
            await asyncio.sleep(0)
            return "{}"
        return self._queue.pop(0)

    async def close(self) -> None:
        self.closed = True


def test_kline_topic_builder():
    assert kline_topic("btcusdt", "5") == "kline.5.BTCUSDT"


def test_symbol_from_kline_topic():
    assert symbol_from_kline_topic("kline.5.BTCUSDT") == "BTCUSDT"
    assert symbol_from_kline_topic("kline_lt.15.ETHUSDT") == "ETHUSDT"
    assert symbol_from_kline_topic("tickers.BTCUSDT") == ""


def test_parse_kline_event_real_bybit_payload_without_symbol_in_data():
    """Bybit v5 kline WS: symbol is only in topic, not in data rows."""
    payload = {
        "topic": "kline.5.BTCUSDT",
        "type": "snapshot",
        "ts": 1672324988882,
        "data": [
            {
                "start": 1672324800000,
                "end": 1672325099999,
                "interval": "5",
                "open": "16649.5",
                "close": "16677",
                "high": "16677",
                "low": "16608",
                "volume": "2.081",
                "turnover": "34666.4005",
                "confirm": False,
                "timestamp": 1672324988882,
            }
        ],
    }
    out = parse_kline_event(payload)
    assert len(out) == 1
    ev = out[0]
    assert ev.symbol == "BTCUSDT"
    assert ev.close == 16677.0
    assert ev.confirm is False


def test_parse_kline_event_single_row():
    payload = {
        "topic": "kline.5.BTCUSDT",
        "data": {
            "symbol": "BTCUSDT",
            "interval": "5",
            "start": 1,
            "end": 2,
            "open": "100",
            "high": "110",
            "low": "90",
            "close": "105",
            "volume": "12.5",
            "turnover": "1300",
            "confirm": True,
        },
    }
    out = parse_kline_event(payload)
    assert len(out) == 1
    ev = out[0]
    assert ev.symbol == "BTCUSDT"
    assert ev.confirm is True
    assert ev.close == 105.0


def test_ws_client_subscribe_and_recv():
    fake_ws = _FakeWS(
        recv_queue=[
            json.dumps({"op": "ping"}),
            json.dumps({"topic": "kline.5.BTCUSDT", "data": {"symbol": "BTCUSDT", "interval": "5"}}),
        ]
    )

    async def _connector(url: str):
        assert url == BYBIT_WS_PUBLIC_MAINNET
        return fake_ws

    async def _run():
        client = BybitWebSocketClient(testnet=True, connector=_connector)
        topics = await client.subscribe_klines(symbols=["BTCUSDT", "ETHUSDT"], interval="5")
        assert topics == ["kline.5.BTCUSDT", "kline.5.ETHUSDT"]
        first = await client.recv_json(timeout_seconds=0.1)
        assert first is None  # ping handled internally
        second = await client.recv_json(timeout_seconds=0.1)
        assert second is not None and second.get("topic") == "kline.5.BTCUSDT"
        await client.close()
        assert fake_ws.closed is True
        sub_payload = json.loads(fake_ws.sent[0])
        assert sub_payload["op"] == "subscribe"
        assert "kline.5.BTCUSDT" in sub_payload["args"]
        assert any(json.loads(x).get("op") == "pong" for x in fake_ws.sent[1:])

    asyncio.run(_run())
