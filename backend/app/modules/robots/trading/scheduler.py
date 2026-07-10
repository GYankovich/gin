#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingScheduler [1]
#/// Исходный модуль `backend/app/modules/robots/trading/scheduler.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/robots/trading/scheduler.py (исправленный)

"""
Шедулер для торговых роботов - управляет сессиями
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy import text

from app.core.database import SessionLocal, try_dispose_pool_on_connectivity_error
from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.scheduler_utils import scheduler_startup_delay
from app.core.background_jobs.repository import enqueue_background_job, has_active_job
from app.core.background_jobs.worker import LANE_HEAVY
from app.modules.robots.trading.runtime import get_trading_orchestrator
from app.modules.robots.scheduling.schedule_policy import should_start_trading_session
from app.modules.robots.trading import queries as trading_queries
from app.modules.robots.trading.brokers.global_websocket import global_websocket_manager

system_log = get_logger("robots.trading.scheduler")


class TradingScheduler:
    """Шедулер для торговых роботов"""

    def __init__(self):
        self.running = False
        self.task = None
        self.check_interval = 30

    async def _get_active_robots(self, db) -> List[Dict]:
        """Активные торговые роботы type=2 с robot_schedules (если есть)."""
        query = trading_queries.build_collect_scheduled_trading_robots_query().format(
            schema=settings.DB_SCHEMA
        )

        try:
            result = db.execute(text(query)).fetchall()
        except Exception as e:
            system_log.error(f"Ошибка получения списка роботов: {e}")
            try_dispose_pool_on_connectivity_error(e)
            return []

        robots = []
        for row in result:
            robots.append({
                "robot_id": row[0],
                "user_id": row[1],
                "token_id": row[2],
                "config": row[3] or {},
                "token": row[4],
                "token_extra_data": row[5] if isinstance(row[5], dict) else {},
                "schedule_type": row[6],
                "interval_seconds": row[7],
                "start_time": row[8],
                "end_time": row[9],
                "weekdays": row[10],
                "token_type": int(row[11]) if len(row) > 11 and row[11] is not None else None,
            })

        return robots

    def _should_start_session(self, robot: Dict) -> bool:
        """Проверка robot_schedules / config.risk (BRD-ARCH-04 этап 5)."""
        return should_start_trading_session(robot)

    async def _run_session(self, robot: Dict):
        """Запускает сессию для одного робота"""
        robot_id = robot["robot_id"]
        system_log.info(f"🤖 Запуск торговой сессии для робота {robot_id}")

        def log_func(msg):
            system_log.debug(f"[ROBOT_{robot_id}] {msg}")

        session = None
        try:
            from app.modules.robots.trading.brokers.routing import (
                BrokerTokenMismatchError,
                enforce_broker_for_token,
            )

            cfg = dict(robot.get("config") or {})
            try:
                broker_type = enforce_broker_for_token(
                    cfg,
                    token_type=robot.get("token_type"),
                    mutate=True,
                    require_token=True,
                )
            except (BrokerTokenMismatchError, ValueError) as exc:
                system_log.error(
                    "❌ Робот %s: отказ запуска — broker/token mismatch: %s",
                    robot_id,
                    exc,
                )
                return

            result = await get_trading_orchestrator().run_live_session(
                schema=settings.DB_SCHEMA,
                robot_id=robot_id,
                user_id=robot["user_id"],
                token_id=robot["token_id"],
                token=robot["token"],
                config=cfg,
                db=None,
                log_func=log_func,
                token_extra_data=robot.get("token_extra_data"),
                token_type=robot.get("token_type"),
            )
            system_log.info(
                "✅ Сессия робота %s завершена: %s (broker=%s)",
                robot_id,
                result.get("status", "unknown"),
                broker_type,
            )

        except asyncio.CancelledError:
            system_log.info(f"⏹️ Сессия робота {robot_id} отменена")
        except Exception as e:
            system_log.error(f"❌ Ошибка в сессии робота {robot_id}: {e}", exc_info=True)

    async def _run_cycle(self):
        """Один цикл: постановка live-сессий в heavy lane."""
        db = SessionLocal()
        try:
            robots = await self._get_active_robots(db)

            if robots:
                system_log.info("📊 Найдено активных торговых роботов: %s", len(robots))
            else:
                system_log.info("📊 Активных торговых роботов нет (type=2, status=1, token active)")

            enqueued = 0
            skipped = 0
            skipped_schedule = 0
            for robot in robots:
                robot_id = robot["robot_id"]

                if not self._should_start_session(robot):
                    skipped_schedule += 1
                    system_log.info(
                        "⏭️ Робот %s: вне окна robot_schedules (broker=%s)",
                        robot_id,
                        (robot.get("config") or {}).get("broker_type"),
                    )
                    continue

                idempotency_key = f"live_session:{robot_id}"
                if has_active_job(db, idempotency_key=idempotency_key):
                    skipped += 1
                    continue

                job_id = enqueue_background_job(
                    db,
                    lane=LANE_HEAVY,
                    job_type="live_trading_session",
                    payload=robot,
                    idempotency_key=idempotency_key,
                )
                if job_id:
                    enqueued += 1
                    system_log.info(
                        "🔄 В очередь heavy: live session robot_id=%s job_id=%s",
                        robot_id,
                        job_id,
                    )

            if enqueued or skipped or skipped_schedule:
                system_log.info(
                    "Торговая очередь: enqueued=%s, skipped_active=%s, skipped_schedule=%s",
                    enqueued,
                    skipped,
                    skipped_schedule,
                )
            db.commit()

        except Exception as e:
            db.rollback()
            system_log.error(f"Ошибка в цикле шедулера: {e}")
            try_dispose_pool_on_connectivity_error(e)
        finally:
            db.close()

    async def _run_loop(self):
        """Основной цикл шедулера"""
        await scheduler_startup_delay("trading")
        system_log.info(f"🔄 Торговый планировщик запущен (интервал: {self.check_interval} сек)")

        while self.running:
            try:
                await self._run_cycle()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_log.error(f"Ошибка в основном цикле: {e}")
                try_dispose_pool_on_connectivity_error(e)
                await asyncio.sleep(5)

        system_log.info("🛑 Торговый планировщик остановлен")

    async def start(self):
        """Запуск шедулера"""
        if self.running:
            system_log.warning("Торговый планировщик уже запущен")
            return

        self.running = True
        self.task = asyncio.create_task(self._run_loop())
        system_log.info("🚀 Запуск торгового планировщика")

    async def stop(self):
        """Остановка шедулера"""
        if not self.running:
            return

        self.running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        await global_websocket_manager.shutdown_all()

        system_log.info("🛑 Торговый планировщик остановлен")

    async def force_run(self, robot_id: int) -> Dict:
        """Принудительный запуск робота через heavy lane (без idempotency)."""
        db = SessionLocal()
        try:
            robots = await self._get_active_robots(db)
            robot = next((r for r in robots if r["robot_id"] == robot_id), None)

            if not robot:
                return {"status": "error", "message": f"Robot {robot_id} not found"}

            job_id = enqueue_background_job(
                db,
                lane=LANE_HEAVY,
                job_type="live_trading_session",
                payload=robot,
                idempotency_key=None,
            )
            db.commit()
            system_log.info(f"🔧 Принудительная постановка в очередь robot_id={robot_id} job_id={job_id}")
            return {"status": "queued", "robot_id": robot_id, "job_id": str(job_id) if job_id else None}
        finally:
            db.close()


# Глобальный экземпляр
trading_scheduler = TradingScheduler()


async def start_trading_scheduler():
    """Запуск шедулера торговых роботов"""
    await trading_scheduler.start()


async def stop_trading_scheduler():
    """Остановка шедулера торговых роботов"""
    await trading_scheduler.stop()


async def force_run_trading_robot(robot_id: int) -> Dict:
    """Принудительный запуск торгового робота"""
    return await trading_scheduler.force_run(robot_id)