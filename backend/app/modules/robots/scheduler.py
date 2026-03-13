import asyncio
import logging
from datetime import datetime, timedelta
from croniter import croniter
from app.modules.robots.trading_service import TradingRobotExecutor
from app.modules.robots.service import robot_service

logger = logging.getLogger(__name__)


class RobotScheduler:
    """
    Планировщик для запуска роботов
    """

    def __init__(self):
        self.running = False
        self.task = None
        # Храним время последнего запуска для каждого токена
        self.last_run_time = {}

    async def _run_cycle(self):
        """
        Один цикл проверки и запуска
        """
        try:
            logger.info("🔄 Running robot scheduler cycle")
            results = await robot_service.run_all_due_updates()

            for result in results:
                token_id = result.get('token_id')
                if "error" in result:
                    logger.warning(f"❌ Token {token_id}: {result['error']}")
                else:
                    logger.info(f"✅ Token {token_id}: "
                                f"accounts: {result.get('accounts_found', 0)}, "
                                f"snapshots: {result.get('snapshots_saved', 0)}")
                    # Запоминаем время успешного запуска
                    self.last_run_time[token_id] = datetime.utcnow()

        except Exception as e:
            logger.error(f"Error in scheduler cycle: {e}", exc_info=True)

    async def _run_loop(self):
        """
        Основной цикл планировщика
        """
        while self.running:
            await self._run_cycle()
            await self._run_trading_robots()  # новые торговые роботы
            # Проверяем каждые 60 секунд
            await asyncio.sleep(60)

    async def start(self):
        """
        Запуск планировщика
        """
        if self.running:
            logger.warning("Scheduler already running")
            return

        self.running = True
        logger.info("🚀 Starting robot scheduler")
        self.task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """
        Остановка планировщика
        """
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Robot scheduler stopped")


# Создаем глобальный экземпляр
scheduler = RobotScheduler()


async def start_scheduler():
    """Запуск планировщика при старте приложения"""
    await scheduler.start()


async def stop_scheduler():
    """Остановка планировщика при остановке приложения"""
    await scheduler.stop()

async def _run_trading_robots(self):
    """
    Запуск всех активных торговых роботов по расписанию
    """
    db = SessionLocal()
    try:
        robots = db.query(TradingRobot).filter(TradingRobot.is_active == 1).all()
        now = datetime.utcnow()

        for robot in robots:
            if not robot.schedule_cron:
                continue

            try:
                # Проверяем по cron, нужно ли запускать сейчас
                cron = croniter(robot.schedule_cron, now)
                prev = cron.get_prev(datetime)

                # Если прошло меньше 60 секунд с предыдущего запуска
                if (now - prev).total_seconds() < 60:
                    logger.info(f"Starting trading robot {robot.id} ({robot.name})")
                    asyncio.create_task(self._run_single_trading_robot(robot.id))

            except Exception as e:
                logger.error(f"Cron error for robot {robot.id}: {e}")

    finally:
        db.close()

async def _run_single_trading_robot(self, robot_id: int):
    """
    Запуск одного торгового робота
    """
    try:
        async with TradingRobotExecutor(robot_id) as executor:
            await executor.execute()
    except Exception as e:
        logger.error(f"Trading robot {robot_id} failed: {e}")