#///EPIC Modules.ITEM Module.TOPIC MoexSecuritiesUpdaterScheduler [1]
"""Cron-driven scheduler for MOEX securities reference updater."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.core.database import SessionLocal, try_dispose_pool_on_connectivity_error
from app.core.logging_config import get_logger
from app.core.scheduler_utils import scheduler_startup_delay
from app.modules.robots.moex_securities_updater import queries
from app.modules.robots.moex_securities_updater.robot import sync_moex_securities_reference

system_log = get_logger("robots.moex_securities.scheduler")


class MoexSecuritiesScheduler:
    def __init__(self) -> None:
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.poll_seconds = 60

    async def run_due_jobs(self) -> Dict[str, Any]:
        db = SessionLocal()
        results: Dict[str, Any] = {"checked": 0, "ran": 0, "details": []}
        try:
            now = datetime.now(timezone.utc)
            sql, params = queries.build_due_cron_jobs_query(now=now)
            due = db.execute(text(sql), params).fetchall()
            results["checked"] = len(due)
            for row in due:
                cron_id = int(row[0])
                robot_name = str(row[1])
                fixed_delay = int(row[2] or 86400)
                if robot_name != queries.ROBOT_NAME:
                    system_log.debug("cron skip unknown robot_name=%s", robot_name)
                    continue
                try:
                    summary = await sync_moex_securities_reference(db)
                    finished = datetime.now(timezone.utc)
                    next_run = finished + timedelta(seconds=max(fixed_delay, 60))
                    mark_sql, mark_params = queries.build_mark_cron_run_query(
                        cron_id=cron_id,
                        last_run=finished,
                        next_run=next_run,
                    )
                    db.execute(text(mark_sql), mark_params)
                    db.commit()
                    results["ran"] += 1
                    results["details"].append(
                        {
                            "robot_name": robot_name,
                            "summary": summary,
                            "next_run": next_run.isoformat(),
                        }
                    )
                    system_log.info(
                        "moex_securities_updater ok cron_id=%s next_run=%s summary=%s",
                        cron_id,
                        next_run.isoformat(),
                        summary,
                    )
                except Exception as e:
                    db.rollback()
                    system_log.error(
                        "moex_securities_updater failed cron_id=%s: %s", cron_id, e
                    )
                    results["details"].append(
                        {"robot_name": robot_name, "error": str(e)}
                    )
            return results
        finally:
            db.close()

    async def _run_loop(self) -> None:
        await scheduler_startup_delay("moex_securities_updater")
        while self.running:
            try:
                await self.run_due_jobs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_log.error("moex securities scheduler loop error: %s", e)
                try_dispose_pool_on_connectivity_error(e)
            try:
                await asyncio.sleep(self.poll_seconds)
            except asyncio.CancelledError:
                break

    async def start(self) -> None:
        if self.running:
            system_log.warning("MOEX securities scheduler already running")
            return
        self.running = True
        self.task = asyncio.create_task(self._run_loop())
        system_log.info("MOEX securities scheduler started")

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
        system_log.info("MOEX securities scheduler stopped")

    async def run_once(self) -> Dict[str, Any]:
        return await self.run_due_jobs()


moex_securities_scheduler = MoexSecuritiesScheduler()


async def start_moex_securities_scheduler() -> None:
    await moex_securities_scheduler.start()


async def stop_moex_securities_scheduler() -> None:
    await moex_securities_scheduler.stop()


async def run_moex_securities_update_once() -> Dict[str, Any]:
    return await moex_securities_scheduler.run_once()
