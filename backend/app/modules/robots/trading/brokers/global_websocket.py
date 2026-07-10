from __future__ import annotations

#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingBrokersGlobalWebsocket [1]
#/// Исходный модуль `backend/app/modules/robots/trading/brokers/global_websocket.py` — автоматическая разметка для Obsidian Source Scanner.

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from app.core.logging_config import get_logger
from app.modules.tinvest.websocket.price_manager import PriceStreamManager

logger = get_logger(__name__)


@dataclass
class _ConnectionState:
    manager: PriceStreamManager
    token: str
    subscribers: Dict[str, Set[asyncio.Queue]] = field(default_factory=dict)
    queue_to_figis: Dict[asyncio.Queue, Set[str]] = field(default_factory=dict)
    prices: Dict[str, float] = field(default_factory=dict)
    connected: bool = False
    connected_at: Optional[datetime] = None
    candle_interval: Optional[str] = None
    receiver_task: Optional[asyncio.Task] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class GlobalWebSocketManager:
    """One websocket per (user_id, token, broker_type)."""

    def __init__(self):
        self._states: Dict[Tuple[int, str, str], _ConnectionState] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, user_id: int, token: str, broker_type: str) -> Tuple[int, str, str]:
        return user_id, token, broker_type

    async def ensure_connected(self, user_id: int, token: str, broker_type: str) -> bool:
        key = self._make_key(user_id, token, broker_type)
        async with self._lock:
            state = self._states.get(key)
            if state is None:
                state = _ConnectionState(manager=PriceStreamManager(token), token=token)
                self._states[key] = state

        async with state.lock:
            if state.connected:
                return True
            had_subscribers = bool(state.subscribers)
            try:
                await state.manager.connect()
                state.connected = True
                state.connected_at = datetime.now(timezone.utc)
                if state.receiver_task is None or state.receiver_task.done():
                    state.receiver_task = asyncio.create_task(self._receiver_loop(key))
                if had_subscribers:
                    await self._resubscribe_after_reconnect(state)
                logger.info("WS connected for user=%s broker=%s", user_id, broker_type)
                return True
            except Exception:
                logger.exception("WS connect failed for user=%s broker=%s", user_id, broker_type)
                return False

    async def subscribe(
        self,
        user_id: int,
        token: str,
        broker_type: str,
        figis: List[str],
        queue: asyncio.Queue,
        *,
        candle_interval: Optional[str] = None,
    ) -> Dict[str, str]:
        key = self._make_key(user_id, token, broker_type)
        connected = await self.ensure_connected(user_id, token, broker_type)
        if not connected:
            return {f: "NO_CONNECTION" for f in figis}

        state = self._states[key]
        new_to_ws: List[str] = []
        async with state.lock:
            tracked_figis = state.queue_to_figis.setdefault(queue, set())
            for figi in figis:
                tracked_figis.add(figi)
                listeners = state.subscribers.setdefault(figi, set())
                if not listeners:
                    new_to_ws.append(figi)
                listeners.add(queue)

        result: Dict[str, str] = {}
        if new_to_ws:
            result.update(await state.manager.subscribe(new_to_ws))
        elif figis:
            result = {f: "ALREADY_SUBSCRIBED" for f in figis}

        if candle_interval:
            state.candle_interval = candle_interval
            candle_new = [f for f in figis if f not in state.manager._subscribed_candle_figis]
            if candle_new:
                candle_res = await state.manager.subscribe_candles(candle_new, candle_interval)
                result.update({f"{k}:candle": v for k, v in candle_res.items()})
        return result

    async def force_resubscribe(self, user_id: int, token: str, broker_type: str) -> bool:
        """Повторно отправляет подписки на брокера (после тихого обрыва WS)."""
        key = self._make_key(user_id, token, broker_type)
        state = self._states.get(key)
        if not state:
            return False
        async with state.lock:
            if not state.connected:
                return False
            if not state.subscribers:
                return False
            await self._resubscribe_after_reconnect(state)
        return True

    async def unsubscribe(
        self,
        user_id: int,
        token: str,
        broker_type: str,
        figis: List[str],
        queue: asyncio.Queue,
    ) -> None:
        key = self._make_key(user_id, token, broker_type)
        state = self._states.get(key)
        if not state:
            return

        to_remove_ws: List[str] = []
        async with state.lock:
            tracked_figis = state.queue_to_figis.get(queue, set())
            for figi in figis:
                tracked_figis.discard(figi)
                listeners = state.subscribers.get(figi)
                if listeners:
                    listeners.discard(queue)
                    if not listeners:
                        to_remove_ws.append(figi)
                        state.subscribers.pop(figi, None)
            if not tracked_figis and queue in state.queue_to_figis:
                state.queue_to_figis.pop(queue, None)

        if to_remove_ws:
            await self._send_unsubscribe(state, to_remove_ws)

    async def get_last_price(self, user_id: int, token: str, broker_type: str, figi: str) -> Optional[float]:
        state = self._states.get(self._make_key(user_id, token, broker_type))
        if not state:
            return None
        return state.prices.get(figi)

    async def get_uptime_seconds(
        self,
        user_id: int,
        token: str,
        broker_type: str,
    ) -> Optional[float]:
        """Сколько секунд открыто глобальное WS-соединение (None если не подключено)."""
        state = self._states.get(self._make_key(user_id, token, broker_type))
        if not state or not state.connected or not state.connected_at:
            return None
        return (datetime.now(timezone.utc) - state.connected_at).total_seconds()

    async def close(self, user_id: int, token: str, broker_type: str, queue: Optional[asyncio.Queue] = None) -> None:
        key = self._make_key(user_id, token, broker_type)
        state = self._states.get(key)
        if not state:
            return

        if queue is None:
            async with state.lock:
                await self._close_state(key, state)
            return

        async with state.lock:
            figis = list(state.queue_to_figis.get(queue, set()))
        if figis:
            await self.unsubscribe(user_id, token, broker_type, figis, queue)

    async def shutdown_all(self) -> None:
        async with self._lock:
            items = list(self._states.items())
        for key, state in items:
            async with state.lock:
                await self._close_state(key, state)

    async def _resubscribe_after_reconnect(self, state: _ConnectionState) -> None:
        figis = list(state.subscribers.keys())
        if not figis:
            return
        state.manager._subscribed_figis.clear()
        state.manager._subscribed_candle_figis.clear()
        try:
            price_res = await state.manager.subscribe(figis)
            logger.info(
                "WS resubscribed lastPrice for %s figis (sample status: %s)",
                len(figis),
                next(iter(price_res.values()), "?"),
            )
            if state.candle_interval:
                candle_res = await state.manager.subscribe_candles(figis, state.candle_interval)
                logger.info(
                    "WS resubscribed candles interval=%s for %s figis",
                    state.candle_interval,
                    len(candle_res),
                )
        except Exception:
            logger.exception("WS resubscribe failed for %s figis", len(figis))

    async def _send_unsubscribe(self, state: _ConnectionState, figis: List[str]) -> None:
        if not state.connected or not state.manager.websocket:
            return
        try:
            import json

            instruments = [{"figi": f, "instrumentId": f} for f in figis]
            payload = {
                "subscribeLastPriceRequest": {
                    "subscriptionAction": "SUBSCRIPTION_ACTION_UNSUBSCRIBE",
                    "instruments": instruments,
                }
            }
            await state.manager.websocket.send(json.dumps(payload))
            logger.info("WS unsubscribe sent for %s figis", len(figis))
        except Exception:
            logger.exception("WS unsubscribe failed")

    async def _receiver_loop(self, key: Tuple[int, str, str]) -> None:
        while True:
            state = self._states.get(key)
            if not state:
                return
            try:
                msg = await state.manager.receive_once(timeout=1.0)
                if not msg:
                    if not state.manager.connected or not state.manager.websocket:
                        state.connected = False
                        state.connected_at = None
                        logger.warning(
                            "Market data WS disconnected (user=%s), reconnecting...", key[0]
                        )
                        await asyncio.sleep(1)
                        if not await self.ensure_connected(*key):
                            await asyncio.sleep(2)
                    continue

                if "ping" in msg and state.manager.websocket:
                    try:
                        await state.manager.websocket.send(json.dumps({"pong": msg["ping"]}))
                    except Exception:
                        pass
                    continue

                if "lastPrice" in msg:
                    price_data = msg["lastPrice"]
                    figi = price_data.get("figi")
                    price = state.manager._parse_price(price_data.get("price"))
                    if figi is None or price is None:
                        continue
                    state.prices[figi] = price
                    payload = {"type": "price", "figi": figi, "price": price}
                    listeners = list(state.subscribers.get(figi, set()))
                    for q in listeners:
                        self._put_nowait_drop_oldest(q, payload)
                    continue

                if "candle" in msg:
                    candle_raw = msg["candle"]
                    figi = candle_raw.get("figi")
                    if not figi:
                        continue
                    candle = state.manager.ws_candle_to_api_dict(candle_raw)
                    close_price = state.manager._parse_price(candle.get("close"))
                    if close_price is not None:
                        state.prices[figi] = close_price
                    if not candle.get("isComplete"):
                        continue
                    payload = {
                        "type": "candle_closed",
                        "figi": figi,
                        "candle": candle,
                        "price": close_price,
                    }
                    listeners = list(state.subscribers.get(figi, set()))
                    for q in listeners:
                        self._put_nowait_drop_oldest(q, payload)
                    continue

                if "lastPrice" not in msg and "candle" not in msg:
                    # When broker WS drops, receive_once returns None immediately (no await inside) —
                    # without a sleep this becomes a tight loop and starves the event loop (REST hangs).
                    pass
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("WS receiver loop error, reconnecting")
                try:
                    await state.manager.close()
                except Exception:
                    pass
                state.connected = False
                state.connected_at = None
                await asyncio.sleep(1)
                if not await self.ensure_connected(*key):
                    await asyncio.sleep(3)

    async def _close_state(self, key: Tuple[int, str, str], state: _ConnectionState) -> None:
        if state.receiver_task and not state.receiver_task.done():
            state.receiver_task.cancel()
            await asyncio.gather(state.receiver_task, return_exceptions=True)
        await state.manager.close()
        state.connected = False
        state.connected_at = None
        state.subscribers.clear()
        state.queue_to_figis.clear()
        self._states.pop(key, None)
        logger.info("WS closed for key=%s", key)

    @staticmethod
    def _put_nowait_drop_oldest(queue: asyncio.Queue, item: Dict[str, object]) -> None:
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            pass
        try:
            queue.get_nowait()
        except Exception:
            pass
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            pass


global_websocket_manager = GlobalWebSocketManager()
