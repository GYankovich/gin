"""Lane worker pools: portfolio and heavy concurrency limits."""

from __future__ import annotations



import asyncio

import logging

from typing import Dict, List, Optional



from app.core.background_jobs.handlers import execute_job_handler

from app.core.background_jobs.repository import (

    claim_next_background_job,

    complete_background_job,

    fail_background_job,

    fail_orphaned_live_session_jobs,

    fail_stale_background_jobs,

)

from app.core.config import settings

from app.core.database import SessionLocal, try_dispose_pool_on_connectivity_error

from app.core.rest_logging_middleware import get_rest_inflight



logger = logging.getLogger(__name__)



LANE_PORTFOLIO = "portfolio"

LANE_HEAVY = "heavy"



_pools: Dict[str, "LaneWorkerPool"] = {}

_embedded_job_semaphore: Optional[asyncio.Semaphore] = None





def _embedded_job_gate() -> Optional[asyncio.Semaphore]:

    global _embedded_job_semaphore

    if not settings.WORKER_EMBEDDED_ENABLED:

        return None

    if _embedded_job_semaphore is None:

        _embedded_job_semaphore = asyncio.Semaphore(int(settings.EMBEDDED_BACKGROUND_MAX_CONCURRENT))

    return _embedded_job_semaphore





class LaneWorkerPool:

    def __init__(self, lane: str, concurrency: int):

        self.lane = lane

        self.concurrency = max(1, int(concurrency))

        self._running = False

        self._tasks: List[asyncio.Task] = []



    async def start(self) -> None:

        if self._running:

            return

        self._running = True

        db_boot = SessionLocal()
        try:
            n = fail_orphaned_live_session_jobs(db_boot, lane=self.lane)
            if n:
                db_boot.commit()
                logger.warning(
                    "lane=%s reset %s orphaned live_trading_session jobs on worker start",
                    self.lane,
                    n,
                )
        except Exception as exc:
            db_boot.rollback()
            logger.warning("lane=%s orphan live session reset failed: %s", self.lane, exc)
        finally:
            db_boot.close()

        for worker_id in range(self.concurrency):

            task = asyncio.create_task(

                self._worker_loop(worker_id),

                name=f"lane-worker-{self.lane}-{worker_id}",

            )

            self._tasks.append(task)

        logger.info("Lane worker pool started lane=%s concurrency=%s", self.lane, self.concurrency)



    async def stop(self) -> None:

        if not self._running:

            return

        self._running = False

        for task in self._tasks:

            task.cancel()

        if self._tasks:

            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

        logger.info("Lane worker pool stopped lane=%s", self.lane)



    async def _maybe_defer_for_rest(self) -> bool:

        """True если нужно подождать — REST-запросы в процессе (embedded)."""

        if self.lane == LANE_HEAVY:

            return False

        if not settings.WORKER_EMBEDDED_ENABLED or not settings.WORKER_DEFER_WHILE_REST_BUSY:

            return False

        if get_rest_inflight() <= 0:

            return False

        await asyncio.sleep(0.25)

        return True



    async def _worker_loop(self, worker_id: int) -> None:

        poll = float(settings.WORKER_POLL_INTERVAL_SECONDS)

        stale_sweep_every = 30.0

        loops_since_sweep = 0



        while self._running:

            try:

                if await self._maybe_defer_for_rest():

                    continue



                loops_since_sweep += 1

                if loops_since_sweep >= int(stale_sweep_every / max(poll, 0.1)):

                    loops_since_sweep = 0

                    db_sweep = SessionLocal()

                    try:

                        n = fail_stale_background_jobs(

                            db_sweep,

                            stale_seconds=int(settings.BACKGROUND_JOB_STALE_SECONDS),

                        )

                        if n:

                            db_sweep.commit()

                            logger.warning("lane=%s marked %s stale jobs failed", self.lane, n)

                    finally:

                        db_sweep.close()



                if await self._maybe_defer_for_rest():

                    continue



                db = SessionLocal()

                job = None

                try:

                    job = claim_next_background_job(db, lane=self.lane)

                    if not job:

                        db.rollback()

                    else:

                        db.commit()

                except Exception:

                    db.rollback()

                    raise

                finally:

                    db.close()



                if not job:

                    await asyncio.sleep(poll)

                    continue



                job_id = job["id"]

                job_type = str(job["job_type"])

                logger.info(

                    "worker lane=%s id=%s type=%s worker=%s",

                    self.lane,

                    job_id,

                    job_type,

                    worker_id,

                )



                gate = _embedded_job_gate()

                try:

                    if gate is not None:

                        await gate.acquire()

                    await asyncio.sleep(0)

                    await execute_job_handler(job_type, dict(job.get("payload") or {}))

                    db_done = SessionLocal()

                    try:

                        complete_background_job(db_done, job_id, message="done")

                        db_done.commit()

                    finally:

                        db_done.close()

                except asyncio.CancelledError:

                    raise

                except Exception as exc:

                    logger.exception("job failed lane=%s id=%s type=%s", self.lane, job_id, job_type)

                    try_dispose_pool_on_connectivity_error(exc)

                    db_fail = SessionLocal()

                    try:

                        fail_background_job(db_fail, job_id, str(exc))

                        db_fail.commit()

                    finally:

                        db_fail.close()

                finally:

                    if gate is not None:

                        gate.release()



            except asyncio.CancelledError:

                break

            except Exception as exc:

                logger.error("lane worker loop error lane=%s worker=%s: %s", self.lane, worker_id, exc)

                try_dispose_pool_on_connectivity_error(exc)

                await asyncio.sleep(poll)





def _lane_concurrency(lane: str) -> int:

    if lane == LANE_PORTFOLIO:

        return int(settings.LANE_PORTFOLIO_CONCURRENCY)

    if lane == LANE_HEAVY:

        return int(settings.LANE_HEAVY_CONCURRENCY)

    return 1





async def start_embedded_lane_workers(lanes: Optional[List[str]] = None) -> None:

    if not settings.WORKER_EMBEDDED_ENABLED:

        logger.info("Embedded lane workers disabled (WORKER_EMBEDDED_ENABLED=false)")

        return

    target = lanes or [LANE_PORTFOLIO, LANE_HEAVY]



    async def _start_lane(lane: str) -> None:

        pool = LaneWorkerPool(lane, _lane_concurrency(lane))

        _pools[lane] = pool

        await pool.start()



    await asyncio.gather(*(_start_lane(lane) for lane in target))





async def stop_embedded_lane_workers() -> None:

    for pool in list(_pools.values()):

        await pool.stop()

    _pools.clear()





async def run_standalone_lane_worker(lane: str) -> None:

    """Blocking entry for `python run.py worker --lane portfolio|heavy`."""

    global _embedded_job_semaphore

    _embedded_job_semaphore = None

    pool = LaneWorkerPool(lane, _lane_concurrency(lane))

    await pool.start()

    try:

        while True:

            await asyncio.sleep(3600)

    except asyncio.CancelledError:

        pass

    finally:

        await pool.stop()

