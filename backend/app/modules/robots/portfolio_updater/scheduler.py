#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsPortfolioUpdaterScheduler [1]
#/// Исходный модуль `backend/app/modules/robots/portfolio_updater/scheduler.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/robots/portfolio_updater/scheduler.py
from typing import Dict, Any, List
import asyncio
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, try_dispose_pool_on_connectivity_error
from app.core.logging_config import get_logger
from app.core.scheduler_utils import scheduler_startup_delay
from app.core.background_jobs.repository import enqueue_background_job
from app.core.background_jobs.worker import LANE_PORTFOLIO
from app.modules.robots.portfolio_updater.robot import PortfolioUpdaterRobot
from . import queries

# Получаем логгер для планировщика
system_log = get_logger("robots.portfolio.scheduler")


class PortfolioUpdaterScheduler:
    """
    Планировщик для робота обновления портфеля
    Запускает цикл обновления по расписанию
    """

    def __init__(self):
        self.robot = PortfolioUpdaterRobot("scheduler")
        self.schema = self.robot.schema
        self.running = False
        self.task = None
        self.interval_seconds = 60  # Проверяем каждую минуту

    async def get_robots_for_update(self, db: Session) -> List[Dict[str, Any]]:
        """
        Получает активных портфельных роботов
        """
        query = queries.build_get_active_portfolio_robots_query().format(
            schema=self.schema
        )

        results = db.execute(
            text(query),
            {
                "robot_type": 1,  # PORTFOLIO_SNAPSHOT
                "status_active": 1  # ACTIVE
            }
        ).fetchall()

        robots = []
        from app.modules.robots.trading.brokers.routing import enforce_broker_for_token
        for row in results:
            token_type = int(row[6]) if len(row) > 6 and row[6] is not None else None
            broker_type = enforce_broker_for_token(
                None,
                token_type=token_type,
                token_type_name=str(row[4] or ""),
                mutate=False,
                require_token=True,
            )
            robots.append({
                "robot_id": row[0],
                "user_id": row[1],
                "token_id": row[2],
                "token": row[3],
                "broker_type": broker_type,
                "token_extra_data": row[5] if isinstance(row[5], dict) else {},
                "token_type": token_type,
            })

        return robots

    async def run_update_cycle(self, db: Session) -> Dict[str, Any]:
        """
        Ставит в очередь portfolio lane задачи на каждого активного робота.
        """
        results = {
            "total": 0,
            "enqueued": 0,
            "skipped_duplicate": 0,
        }

        robots = await self.get_robots_for_update(db)
        results["total"] = len(robots)

        if robots:
            system_log.info(f"🔄 Найдено {len(robots)} портфельных роботов — постановка в очередь")

        for robot_data in robots:
            job_id = enqueue_background_job(
                db,
                lane=LANE_PORTFOLIO,
                job_type="portfolio_sync",
                payload=robot_data,
                idempotency_key=f"portfolio_sync:{robot_data['robot_id']}",
            )
            if job_id:
                results["enqueued"] += 1
                system_log.debug(
                    "   queued portfolio_sync robot_id=%s job_id=%s",
                    robot_data["robot_id"],
                    job_id,
                )
            else:
                results["skipped_duplicate"] += 1

        if robots:
            system_log.info(
                "📊 Портфельная очередь: всего=%s, enqueued=%s, duplicate_skip=%s",
                results["total"],
                results["enqueued"],
                results["skipped_duplicate"],
            )

        return results

    async def _run_loop(self):
        """
        Основной цикл планировщика
        """
        await scheduler_startup_delay("portfolio")
        system_log.info(f"🔄 Портфельный планировщик запущен (интервал: {self.interval_seconds} сек)")

        while self.running:
            try:
                cycle_start = datetime.now(timezone.utc)
                system_log.debug("Начало цикла обновления портфелей")

                # Создаем сессию БД
                db = SessionLocal()
                try:
                    await self.run_update_cycle(db)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()

                # Вычисляем время до следующего запуска
                elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
                wait_time = max(1, self.interval_seconds - elapsed)

                if wait_time > 0 and self.running:
                    system_log.debug(f"Ожидание {wait_time:.1f} сек до следующего цикла")
                    await asyncio.sleep(wait_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                system_log.error(f"Ошибка в цикле портфельного планировщика: {e}")
                try_dispose_pool_on_connectivity_error(e)
                await asyncio.sleep(5)

    async def start(self):
        """
        Запуск планировщика
        """
        if self.running:
            system_log.warning("Портфельный планировщик уже запущен")
            return

        self.running = True
        self.task = asyncio.create_task(self._run_loop())
        system_log.info("🚀 Портфельный планировщик запущен")

    async def stop(self):
        """
        Остановка планировщика
        """
        if not self.running:
            return

        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        system_log.info("🛑 Портфельный планировщик остановлен")

    async def run_once(self) -> Dict[str, Any]:
        """
        Принудительный однократный запуск (для тестирования)
        """
        system_log.info("🔧 Принудительный однократный запуск портфельного обновления")
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


# Глобальный экземпляр
portfolio_scheduler = PortfolioUpdaterScheduler()


async def start_portfolio_scheduler():
    """Запуск портфельного планировщика"""
    await portfolio_scheduler.start()


async def stop_portfolio_scheduler():
    """Остановка портфельного планировщика"""
    await portfolio_scheduler.stop()


async def run_portfolio_update_once():
    """Принудительный однократный запуск"""
    return await portfolio_scheduler.run_once()