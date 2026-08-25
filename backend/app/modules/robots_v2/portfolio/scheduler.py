"""Portfolio updater scheduler — reads robots_v2 (type=1), not legacy robots."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.background_jobs.repository import enqueue_background_job
from app.core.background_jobs.repository import fail_stale_queued_portfolio_jobs
from app.core.background_jobs.worker import LANE_PORTFOLIO
from app.core.database import SessionLocal, try_dispose_pool_on_connectivity_error
from app.core.logging_config import get_logger
from app.core.scheduler_utils import scheduler_startup_delay
from app.modules.robots.trading.brokers.routing import enforce_broker_for_token
from app.modules.robots_v2.portfolio.queries import build_get_active_portfolio_v2_robots_query

system_log = get_logger("robots_v2.portfolio.scheduler")


class PortfolioV2Scheduler:
    def __init__(self) -> None:
        from app.core.config import settings

        self.schema = settings.DB_SCHEMA or "public"
        self.running = False
        self.task: asyncio.Task | None = None
        self.interval_seconds = 60

    async def get_robots_for_update(self, db: Session) -> list[dict[str, Any]]:
        query = build_get_active_portfolio_v2_robots_query(schema=self.schema)
        results = db.execute(
            text(query),
            {"robot_type": 1, "status_active": 1},
        ).fetchall()

        robots: list[dict[str, Any]] = []
        for row in results:
            token_type = int(row.token_type) if row.token_type is not None else None
            broker_type = enforce_broker_for_token(
                None,
                token_type=token_type,
                token_type_name=str(row.broker_type or ""),
                mutate=False,
                require_token=True,
            )
            robots.append(
                {
                    "robot_id": int(row.robot_id),
                    "user_id": int(row.user_id),
                    "token_id": int(row.token_id),
                    "token": row.token_value,
                    "broker_type": broker_type,
                    "token_extra_data": row.token_extra_data if isinstance(row.token_extra_data, dict) else {},
                    "token_type": token_type,
                }
            )
        return robots

    async def run_update_cycle(self, db: Session) -> dict[str, Any]:
        from app.core.config import settings

        results = {"total": 0, "enqueued": 0, "skipped_duplicate": 0, "stale_queued_failed": 0}
        stale_n = fail_stale_queued_portfolio_jobs(
            db,
            stale_seconds=int(settings.PORTFOLIO_SYNC_QUEUED_STALE_SECONDS),
        )
        if stale_n:
            results["stale_queued_failed"] = stale_n
            system_log.warning(
                "Portfolio v2: failed %s stale queued portfolio_sync jobs",
                stale_n,
            )

        robots = await self.get_robots_for_update(db)
        results["total"] = len(robots)

        if robots:
            system_log.info("Найдено %s portfolio v2 роботов — постановка в очередь", len(robots))

        for robot_data in robots:
            job_id = enqueue_background_job(
                db,
                lane=LANE_PORTFOLIO,
                job_type="portfolio_sync",
                payload=robot_data,
                idempotency_key=f"portfolio_sync:v2:{robot_data['robot_id']}",
            )
            if job_id:
                results["enqueued"] += 1
            else:
                results["skipped_duplicate"] += 1

        if robots:
            system_log.info(
                "Portfolio v2 queue: total=%s enqueued=%s duplicate_skip=%s",
                results["total"],
                results["enqueued"],
                results["skipped_duplicate"],
            )
        return results

    async def _run_loop(self) -> None:
        await scheduler_startup_delay("portfolio")
        system_log.info("Portfolio v2 scheduler started (interval=%ss)", self.interval_seconds)

        while self.running:
            try:
                cycle_start = datetime.now(timezone.utc)
                db = SessionLocal()
                try:
                    await self.run_update_cycle(db)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()

                elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = max(1, self.interval_seconds - elapsed)
                if wait_time > 0 and self.running:
                    await asyncio.sleep(wait_time)
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_log.error("Portfolio v2 scheduler error: %s", e)
                try_dispose_pool_on_connectivity_error(e)
                await asyncio.sleep(5)

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run_loop())
        system_log.info("Portfolio v2 scheduler task created")

    async def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        system_log.info("Portfolio v2 scheduler stopped")

    async def run_once(self) -> dict[str, Any]:
        db = SessionLocal()
        try:
            result = await self.run_update_cycle(db)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


portfolio_v2_scheduler = PortfolioV2Scheduler()


async def start_portfolio_v2_scheduler() -> None:
    await portfolio_v2_scheduler.start()


async def stop_portfolio_v2_scheduler() -> None:
    await portfolio_v2_scheduler.stop()


async def run_portfolio_update_once() -> dict[str, Any]:
    """Force one portfolio enqueue cycle (robots_v2 type=1)."""
    return await portfolio_v2_scheduler.run_once()
