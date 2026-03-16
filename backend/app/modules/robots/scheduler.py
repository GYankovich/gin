# app/modules/robots/scheduler.py
import asyncio
import logging
from datetime import datetime

from app.core.database import SessionLocal
from app.modules.robots.portfolio_updater.scheduler import PortfolioUpdaterScheduler
from app.modules.robots.common.logger import get_logger

logger = logging.getLogger(__name__)
system_log = get_logger("SYSTEM", "SCHEDULER")


class RobotScheduler:
    """
    Главный планировщик всех роботов
    """

    def __init__(self):
        self.running = False
        self.task = None
        self.portfolio_updater = PortfolioUpdaterScheduler()

    async def _run_cycle(self):
        """Один цикл работы планировщика"""
        db = SessionLocal()

        try:
            system_log.info("🔄 Запуск цикла обновления")

            # Запускаем обновление портфелей
            result = await self.portfolio_updater.run_update_cycle(db)

            system_log.info(f"✅ Цикл завершен: {result}")

        except Exception as e:
            system_log.error(f"❌ Ошибка в цикле: {e}")
        finally:
            db.close()

    async def _run_loop(self):
        """Основной цикл"""
        while self.running:
            await self._run_cycle()
            # Проверяем каждые 60 секунд
            await asyncio.sleep(60)

    async def start(self):
        """Запуск планировщика"""
        if self.running:
            system_log.warning("Планировщик уже запущен")
            return

        self.running = True
        system_log.info("🚀 Запуск главного планировщика")
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

    async def force_update(self, db, token_id: int = None):
        """
        Принудительное обновление (для API)
        """
        if token_id:
            # Обновляем конкретный токен
            from app.modules.robots.portfolio_updater.robot import PortfolioUpdaterRobot
            robot = PortfolioUpdaterRobot("manual")
            robot.db = db

            query = "SELECT id, user_id, token FROM ganaly.api_tokens WHERE id = :id AND is_active = 1"
            token_data = db.execute(text(query), {"id": token_id}).first()

            if not token_data:
                return {"error": f"Token {token_id} not found"}

            result = await robot.run(
                user_id=token_data[1],
                token_id=token_id,
                token=token_data[2]
            )
            return {"result": result}
        else:
            # Обновляем всё
            return await self.portfolio_updater.run_update_cycle(db)


# Глобальный экземпляр
scheduler = RobotScheduler()


async def start_scheduler():
    """Запуск планировщика"""
    await scheduler.start()


async def stop_scheduler():
    """Остановка планировщика"""
    await scheduler.stop()