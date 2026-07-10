"""Shared async HTTP client for T-Invest REST calls with transport recovery."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_shared_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()
_limiters: Dict[str, "_TokenRateLimiter"] = {}
_limiters_lock = asyncio.Lock()

_TRANSPORT_ERRORS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
    httpx.CloseError,
)


class _TokenRateLimiter:
    def __init__(self, limit: int = 60, window_seconds: int = 60):
        self._limit = int(limit)
        self._window = timedelta(seconds=int(window_seconds))
        self._events: Deque[datetime] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = datetime.now(timezone.utc)
                boundary = now - self._window
                while self._events and self._events[0] <= boundary:
                    self._events.popleft()
                if len(self._events) < self._limit:
                    self._events.append(now)
                    return
                wait_for = (self._events[0] + self._window - now).total_seconds()
            await asyncio.sleep(max(0.01, wait_for))


def is_transport_error(exc: BaseException) -> bool:
    if isinstance(exc, _TRANSPORT_ERRORS):
        return True
    cur: BaseException | None = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, _TRANSPORT_ERRORS):
            return True
        cur = cur.__cause__ or getattr(cur, "__context__", None)
    return False


async def reset_shared_http_client() -> None:
    """Закрывает и сбрасывает shared client — следующий запрос откроет новое соединение."""
    global _shared_client
    async with _client_lock:
        if _shared_client is not None:
            try:
                if not _shared_client.is_closed:
                    await _shared_client.aclose()
            except Exception as exc:
                logger.debug("shared httpx client close: %s", exc)
            _shared_client = None


async def get_shared_http_client() -> httpx.AsyncClient:
    global _shared_client
    async with _client_lock:
        if _shared_client is None or _shared_client.is_closed:
            _shared_client = httpx.AsyncClient(
                verify=False,
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            )
        return _shared_client


async def close_shared_http_client() -> None:
    await reset_shared_http_client()


async def get_tinvest_rate_limiter(token: str) -> _TokenRateLimiter:
    key = token or "anonymous"
    async with _limiters_lock:
        limiter = _limiters.get(key)
        if limiter is None:
            limiter = _TokenRateLimiter(limit=60, window_seconds=60)
            _limiters[key] = limiter
        return limiter


async def post_with_transport_recovery(
    url: str,
    *,
    headers: Dict[str, str],
    json: Optional[Dict] = None,
    timeout: float = 30.0,
    token: str = "",
    max_attempts: int = 3,
) -> httpx.Response:
    """
    POST через shared client с rate-limit и восстановлением transport-соединения.

    При NetworkError/timeout закрывает httpx client и повторяет запрос с backoff.
    HTTP-ошибки (4xx/5xx) не ретраятся — их обрабатывает вызывающий код.
    """
    limiter = await get_tinvest_rate_limiter(token)
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            await limiter.acquire()
            client = await get_shared_http_client()
            return await client.post(url, json=json, headers=headers, timeout=timeout)
        except _TRANSPORT_ERRORS as exc:
            last_error = exc
            logger.warning(
                "T-Invest HTTP transport error attempt=%s/%s url=%s: %s",
                attempt,
                max_attempts,
                url,
                exc,
            )
            await reset_shared_http_client()
            if attempt < max_attempts:
                await asyncio.sleep(0.5 * attempt)
    assert last_error is not None
    raise last_error
