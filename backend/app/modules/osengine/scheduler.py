"""Фоновый GC кэша OsEngine (опциональный safety-net).

Основной путь: GC при старте OsEngine-бэктеста (OSENGINE_CACHE_GC_ON_BACKTEST_START).
Interval-scheduler по умолчанию выключен (OSENGINE_CACHE_GC_ENABLED=false).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.database import SessionLocal, try_dispose_pool_on_connectivity_error
from app.core.scheduler_utils import scheduler_startup_delay

logger = logging.getLogger("osengine.cache_gc")

_task: Optional[asyncio.Task] = None
_stop = asyncio.Event()


def run_osengine_cache_gc_once() -> Dict[str, Any]:
    """Синхронный проход GC (scheduler / ручной вызов / тесты)."""
    from app.modules.osengine import get_osengine_facade

    db = SessionLocal()
    try:
        facade = get_osengine_facade()
        stats = facade.gc_cache(db)
        db.commit()
        result = {
            "expired_leases": stats.expired_leases,
            "deleted_candle_rows": stats.deleted_candle_rows,
            "deleted_tick_rows": stats.deleted_tick_rows,
            "deleted_depth_rows": stats.deleted_depth_rows,
            "market": facade.market,
        }
        if stats.expired_leases or stats.deleted_candle_rows:
            logger.info(
                "osengine cache gc ok expired_leases=%s deleted_candles=%s",
                stats.expired_leases,
                stats.deleted_candle_rows,
            )
        else:
            logger.debug("osengine cache gc idle (nothing to purge)")
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _loop() -> None:
    await scheduler_startup_delay("osengine_cache_gc")
    while not _stop.is_set():
        try:
            await asyncio.to_thread(run_osengine_cache_gc_once)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("osengine cache gc failed: %s", e)
            try_dispose_pool_on_connectivity_error(e)

        interval = float(settings.OSENGINE_CACHE_GC_INTERVAL_SECONDS)
        try:
            await asyncio.wait_for(_stop.wait(), timeout=max(60.0, interval))
        except asyncio.TimeoutError:
            continue


async def start_osengine_cache_gc_scheduler() -> None:
    global _task
    if not settings.OSENGINE_CACHE_GC_ENABLED:
        logger.info(
            "osengine interval GC disabled (OSENGINE_CACHE_GC_ENABLED=false); "
            "GC runs on backtest start when OSENGINE_CACHE_GC_ON_BACKTEST_START=true"
        )
        return
    if _task and not _task.done():
        return
    _stop.clear()
    _task = asyncio.create_task(_loop(), name="osengine_cache_gc")
    logger.info(
        "osengine interval cache GC started interval=%.0fs (safety-net)",
        float(settings.OSENGINE_CACHE_GC_INTERVAL_SECONDS),
    )


async def stop_osengine_cache_gc_scheduler() -> None:
    global _task
    _stop.set()
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    logger.info("osengine cache GC scheduler stopped")


__all__ = [
    "run_osengine_cache_gc_once",
    "start_osengine_cache_gc_scheduler",
    "stop_osengine_cache_gc_scheduler",
]
