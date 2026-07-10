"""Shared helpers for background schedulers."""
from __future__ import annotations

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Разносим первый тик планировщиков, чтобы не бить в API одним залпом.
_SCHEDULER_START_OFFSETS: dict[str, float] = {
    "portfolio": 0.0,
    "trading": 5.0,
    "dms": 8.0,
    "candle_load": 12.0,
    "corporate_actions": 18.0,
}


async def scheduler_startup_delay(name: str) -> None:
    """Let FastAPI finish startup before heavy background I/O."""
    base = float(settings.SCHEDULER_STARTUP_DELAY_SECONDS)
    extra = float(_SCHEDULER_START_OFFSETS.get(name, 0.0))
    delay = base + extra
    if delay <= 0:
        return
    logger.info("%s: отложенный старт %.1f с (API остаётся доступным)", name, delay)
    await asyncio.sleep(delay)
