from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict


class TokenRateLimiter:
    """Precise sliding-window limiter for one token."""

    def __init__(self, limit: int = 60, window_seconds: int = 60):
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._events: Deque[datetime] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Wait for permit and return waited seconds."""
        waited = 0.0
        while True:
            async with self._lock:
                now = datetime.now(timezone.utc)
                boundary = now - self._window
                while self._events and self._events[0] <= boundary:
                    self._events.popleft()

                if len(self._events) < self._limit:
                    self._events.append(now)
                    return waited

                wait_for = (self._events[0] + self._window - now).total_seconds()
            wait_for = max(0.01, wait_for)
            waited += wait_for
            await asyncio.sleep(wait_for)


_token_limiters: Dict[str, TokenRateLimiter] = {}
_limiters_lock = asyncio.Lock()


async def get_token_rate_limiter(token: str) -> TokenRateLimiter:
    async with _limiters_lock:
        limiter = _token_limiters.get(token)
        if limiter is None:
            limiter = TokenRateLimiter(limit=60, window_seconds=60)
            _token_limiters[token] = limiter
        return limiter
