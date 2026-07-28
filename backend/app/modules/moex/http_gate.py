"""Global limit on concurrent outbound MOEX ISS HTTP calls (one process)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

# BRD-ARCH-02 §3.7: не более 4 параллельных HTTP к MOEX (и др. исходящим загрузчикам в этом процессе).
MOEX_HTTP_CONCURRENCY = 4

_semaphore = asyncio.BoundedSemaphore(MOEX_HTTP_CONCURRENCY)


@asynccontextmanager
async def moex_http_acquire() -> AsyncIterator[None]:
    await _semaphore.acquire()
    try:
        yield
    finally:
        _semaphore.release()
