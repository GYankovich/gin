"""ByBit public websocket client (R4.2 foundation)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Optional

import websockets

from app.modules.bybit.environment import bybit_use_testnet

BYBIT_WS_PUBLIC_MAINNET = "wss://stream.bybit.com/v5/public/linear"


@dataclass
class BybitKlineEvent:
    symbol: str
    interval: str
    start_ms: int
    end_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    confirm: bool
    raw: dict[str, Any]


def kline_topic(symbol: str, interval: str) -> str:
    return f"kline.{interval}.{str(symbol).upper()}"


def symbol_from_kline_topic(topic: str) -> str:
    """Extract symbol from Bybit kline topic (e.g. kline.5.BTCUSDT or kline_lt.5.BTCUSDT)."""
    parts = str(topic or "").strip().split(".")
    if len(parts) < 3:
        return ""
    prefix = parts[0].lower()
    if prefix not in {"kline", "kline_lt"}:
        return ""
    return str(parts[-1]).strip().upper()


def parse_kline_event(payload: dict[str, Any]) -> list[BybitKlineEvent]:
    topic = str(payload.get("topic") or "")
    if not topic.startswith("kline."):
        return []
    topic_symbol = symbol_from_kline_topic(topic)
    data = payload.get("data")
    if isinstance(data, dict):
        rows = [data]
    elif isinstance(data, list):
        rows = [x for x in data if isinstance(x, dict)]
    else:
        rows = []
    out: list[BybitKlineEvent] = []
    for row in rows:
        try:
            row_symbol = str(row.get("symbol") or "").strip().upper()
            symbol = row_symbol or topic_symbol
            if not symbol:
                continue
            out.append(
                BybitKlineEvent(
                    symbol=symbol,
                    interval=str(row.get("interval") or ""),
                    start_ms=int(row.get("start") or 0),
                    end_ms=int(row.get("end") or 0),
                    open=float(row.get("open") or 0),
                    high=float(row.get("high") or 0),
                    low=float(row.get("low") or 0),
                    close=float(row.get("close") or 0),
                    volume=float(row.get("volume") or 0),
                    turnover=float(row.get("turnover") or 0),
                    confirm=bool(row.get("confirm")),
                    raw=row,
                )
            )
        except Exception:
            continue
    return out


class BybitWebSocketClient:
    """Minimal ByBit public WS client for kline stream."""

    def __init__(
        self,
        *,
        testnet: bool = False,
        connect_timeout_seconds: float = 15.0,
        connector: Optional[Callable[[str], Awaitable[Any]]] = None,
    ) -> None:
        del testnet
        self.testnet = bybit_use_testnet()
        self.url = BYBIT_WS_PUBLIC_MAINNET
        self.connect_timeout_seconds = float(connect_timeout_seconds)
        self._connector = connector
        self._ws: Any = None
        self.connected = False

    async def connect(self) -> None:
        if self.connected and self._ws is not None:
            return
        connector = self._connector
        if connector is None:
            async def _default_connect(url: str) -> Any:
                return await websockets.connect(url, ping_interval=20, ping_timeout=10, close_timeout=5)

            connector = _default_connect
        self._ws = await asyncio.wait_for(connector(self.url), timeout=self.connect_timeout_seconds)
        self.connected = True

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None
        self.connected = False

    async def subscribe_klines(self, *, symbols: Iterable[str], interval: str) -> list[str]:
        if not self.connected or self._ws is None:
            await self.connect()
        topics = [kline_topic(symbol, interval) for symbol in symbols if str(symbol or "").strip()]
        if not topics:
            return []
        msg = {"op": "subscribe", "args": topics}
        await self._ws.send(json.dumps(msg))
        return topics

    async def recv_json(self, timeout_seconds: float = 1.0) -> Optional[dict[str, Any]]:
        if not self.connected or self._ws is None:
            return None
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return None
        except Exception:
            self.connected = False
            return None
        try:
            msg = json.loads(raw)
        except Exception:
            return None
        if isinstance(msg, dict) and msg.get("op") == "ping":
            try:
                await self._ws.send(json.dumps({"op": "pong"}))
            except Exception:
                self.connected = False
            return None
        return msg if isinstance(msg, dict) else None
