from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Dict, List


class LiveEventHub:
    """In-memory event fanout for live robot streams."""

    def __init__(self):
        self._subscribers: Dict[int, List[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, robot_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        async with self._lock:
            self._subscribers[robot_id].append(queue)
        return queue

    async def unsubscribe(self, robot_id: int, queue: asyncio.Queue) -> None:
        async with self._lock:
            qs = self._subscribers.get(robot_id, [])
            if queue in qs:
                qs.remove(queue)
            if not qs and robot_id in self._subscribers:
                self._subscribers.pop(robot_id, None)

    async def publish(self, robot_id: int, event: Dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._subscribers.get(robot_id, []))
        for q in targets:
            self._put_nowait_drop_oldest(q, event)

    @staticmethod
    def _put_nowait_drop_oldest(queue: asyncio.Queue, item: Dict[str, Any]) -> None:
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


live_event_hub = LiveEventHub()
