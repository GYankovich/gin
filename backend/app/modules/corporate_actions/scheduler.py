"""Scheduled ETL: TQBR reference + equity dividends (via heavy lane queue)."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.core.database import SessionLocal, try_dispose_pool_on_connectivity_error
from app.core.scheduler_utils import scheduler_startup_delay
from app.core.background_jobs.repository import enqueue_background_job
from app.core.background_jobs.worker import LANE_HEAVY

logger = logging.getLogger("corporate_actions.scheduler")

_task: Optional[asyncio.Task] = None
_stop = asyncio.Event()


async def _loop() -> None:
    await scheduler_startup_delay("corporate_actions")
    while not _stop.is_set():
        db = SessionLocal()
        try:
            job_id = enqueue_background_job(
                db,
                lane=LANE_HEAVY,
                job_type="corporate_actions_dividend_etl",
                payload={},
                idempotency_key="corporate_actions_dividend_etl",
            )
            db.commit()
            if job_id:
                logger.info("enqueued corporate_actions_dividend_etl job_id=%s", job_id)
            else:
                logger.debug("corporate_actions_dividend_etl already queued/running")
        except Exception as e:
            logger.warning("corporate_actions enqueue failed: %s", e)
            try_dispose_pool_on_connectivity_error(e)
            db.rollback()
        finally:
            db.close()

        try:
            await asyncio.wait_for(_stop.wait(), timeout=6 * 3600)
        except asyncio.TimeoutError:
            continue


async def start_corporate_actions_scheduler() -> None:
    global _task
    if _task and not _task.done():
        return
    _stop.clear()
    _task = asyncio.create_task(_loop(), name="corporate_actions_etl")


async def stop_corporate_actions_scheduler() -> None:
    global _task
    _stop.set()
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
