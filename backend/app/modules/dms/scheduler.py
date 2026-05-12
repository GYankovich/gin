#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesDmsScheduler [1]
#/// Исходный модуль `backend/app/modules/dms/scheduler.py` — автоматическая разметка для Obsidian Source Scanner.

import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.core.database import SessionLocal
from app.core.config import settings
from app.core.logging_config import get_logger
from app.modules.dms.service import dms_service
from sqlalchemy import text

system_log = get_logger("dms.scheduler")


class DmsScheduler:
    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.interval_seconds = 60
        self._last_cleanup_day: Optional[str] = None

    async def _run_loop(self):
        system_log.info("DMS scheduler started, interval=%ss", self.interval_seconds)
        while self.running:
            cycle_start = datetime.now(timezone.utc)
            db = SessionLocal()
            try:
                result = await dms_service.process_pending_subscriptions(db)
                if result.get("processed_subscriptions", 0) > 0:
                    system_log.info(
                        "DMS queue processed: subs=%s snapshots=%s universe_rows=%s",
                        result.get("processed_subscriptions", 0),
                        result.get("created_snapshots", 0),
                        result.get("analyzer_written_rows", 0),
                    )
                # Best-effort daily initialization for robots with today's DMS subscriptions.
                active_robots = db.execute(
                    text(
                        f"""
                        SELECT DISTINCT s.robot_id, s.board
                        FROM {settings.DB_SCHEMA}.dms_subscriptions s
                        JOIN {settings.DB_SCHEMA}.robots r ON r.id = s.robot_id
                        WHERE r.status != 0
                          AND s.request_date = CURRENT_DATE
                        LIMIT 200
                        """
                    )
                ).fetchall()
                for robot_id, board in active_robots:
                    try:
                        await dms_service.initialize_trading_day(
                            db=db,
                            user_id=None,  # scheduler/system context
                            robot_id=int(robot_id),
                            board=str(board or "TQBR"),
                            force_refresh_snapshot=False,
                        )
                    except Exception as e:
                        system_log.warning("DMS init-day skipped for robot_id=%s: %s", robot_id, e)
                today_key = datetime.now(timezone.utc).date().isoformat()
                if self._last_cleanup_day != today_key:
                    cleanup_res = await dms_service.cleanup_old_snapshots(db, older_than_days=3)
                    self._last_cleanup_day = today_key
                    if cleanup_res.get("deleted_snapshots", 0) > 0:
                        system_log.info(
                            "DMS cleanup: deleted_snapshots=%s moved_rows=%s",
                            cleanup_res.get("deleted_snapshots", 0),
                            cleanup_res.get("moved_rows", 0),
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_log.error("DMS scheduler cycle error: %s", e)
            finally:
                db.close()

            elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            wait_time = max(1.0, self.interval_seconds - elapsed)
            if self.running:
                await asyncio.sleep(wait_time)
        system_log.info("DMS scheduler stopped")

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._run_loop())

    async def stop(self):
        if not self.running:
            return
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


dms_scheduler = DmsScheduler()


async def start_dms_scheduler():
    await dms_scheduler.start()


async def stop_dms_scheduler():
    await dms_scheduler.stop()
