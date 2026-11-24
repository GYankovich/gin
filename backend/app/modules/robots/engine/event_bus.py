"""In-memory event bus for v2 live stream + recent log ring buffer."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any


class EventBus:
    def __init__(self, *, history_limit: int = 500) -> None:
        self._subscribers: dict[int, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
        self._history: dict[int, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=history_limit))

    def subscribe(self, robot_id: int) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers[robot_id].append(q)
        return q

    def unsubscribe(self, robot_id: int, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subscribers.get(robot_id, [])
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(robot_id, None)

    async def publish(self, robot_id: int, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "robotId": robot_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        self._history[robot_id].append(event)
        for q in list(self._subscribers.get(robot_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest so the latest cycle/positions marks still arrive.
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    def recent(self, robot_id: int, *, limit: int = 100, event_type: str | None = None) -> list[dict[str, Any]]:
        items = list(self._history.get(robot_id, ()))
        if event_type:
            items = [e for e in items if e.get("type") == event_type]
        if limit > 0:
            items = items[-limit:]
        return list(reversed(items))


event_bus = EventBus()
