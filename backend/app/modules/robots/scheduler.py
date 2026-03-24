# app/modules/robots/scheduler.py
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from app.core.database import SessionLocal
from app.modules.robots.portfolio_updater.scheduler import PortfolioUpdaterScheduler
from app.modules.robots.common.logger import get_logger

logger = logging.getLogger(__name__)
system_log = get_logger("SYSTEM", "SCHEDULER")


class RobotScheduler:
    """
    Главный планировщик всех роботов
    Теперь работает с единой структурой robots и robot_schedules
    """

    def __init__(self):
        self.running = False
        self.task = None
        self.portfolio_updater = PortfolioUpdaterScheduler()

    async def _run_cycle(self):
        """Один цикл работы планировщика"""
        db = SessionLocal()

        try:
            system_log.info(f"[{datetime.now()}] 🔄 Запуск цикла обновления")

            # Запускаем обновление портфелей
            portfolio_result = await self.portfolio_updater.run_update_cycle(db)
            system_log.info(f"📊 Портфели: {portfolio_result}")

            system_log.info(f"[{datetime.now()}] ✅ Цикл завершен")

        except Exception as e:
            system_log.error(f"❌ Ошибка в цикле: {e}", exc_info=True)
        finally:
            db.close()

    async def _run_loop(self):
        """Основной цикл - проверяем каждые 10 секунд"""
        while self.running:
            try:
                await self._run_cycle()
                # Проверяем каждые 10 секунд для более точного интервала
                await asyncio.sleep(10)
            except Exception as e:
                system_log.error(f"Ошибка в цикле: {e}")
                await asyncio.sleep(5)

    async def start(self):
        """Запуск планировщика"""
        if self.running:
            system_log.warning("Планировщик уже запущен")
            return

        self.running = True
        system_log.info("🚀 Запуск главного планировщика (интервал проверки: 10 сек)")
        self.task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Остановка планировщика"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        system_log.info("🛑 Планировщик остановлен")

    async def force_update(self, db, robot_id: int = None):
        """
        Принудительное обновление (для API)
        """
        if robot_id:
            # Обновляем конкретного робота
            from app.modules.robots.portfolio_updater.robot import PortfolioUpdaterRobot

            # Получаем данные робота
            query = """
                SELECT r.id, r.user_id, r.token_id, at.token
                FROM {schema}.robots r
                INNER JOIN {schema}.api_tokens at ON r.token_id = at.id
                WHERE r.id = :robot_id AND r.status = 0
            """.format(schema=PortfolioUpdaterRobot.schema)

            robot_data = db.execute(text(query), {"robot_id": robot_id}).first()

            if not robot_data:
                return {"error": f"Robot {robot_id} not found or inactive"}

            robot = PortfolioUpdaterRobot("manual")
            robot.db = db

            result = await robot.execute(
                robot_id=robot_data[0],
                user_id=robot_data[1],
                token_id=robot_data[2],
                token=robot_data[3]
            )
            return {"result": result}
        else:
            # Обновляем всё
            return {
                "portfolio": await self.portfolio_updater.run_update_cycle(db)
            }


# Глобальный экземпляр
scheduler = RobotScheduler()


async def start_scheduler():
    """Запуск планировщика"""
    await scheduler.start()


async def stop_scheduler():
    """Остановка планировщика"""
    await scheduler.stop()