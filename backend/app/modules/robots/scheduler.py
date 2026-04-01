# app/modules/robots/scheduler.py
import asyncio
import logging
from app.core.logging_config import get_logger

system_log = get_logger("robots.scheduler")


class MainScheduler:
    """Главный планировщик роботов"""

    def __init__(self):
        self.running = False
        self.task = None

    async def start(self):
        if self.running:
            return
        self.running = True
        system_log.info("🚀 Запуск главного планировщика (интервал проверки: 10 сек)")
        self.task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
        system_log.info("🛑 Главный планировщик остановлен")

    async def _run_loop(self):
        while self.running:
            try:
                await self._check_robots()
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_log.error(f"Ошибка в цикле планировщика: {e}")
                await asyncio.sleep(5)

    async def _check_robots(self):
        """Проверяет и запускает роботов"""
        system_log.debug("Проверка роботов...")
        # Здесь логика проверки роботов


scheduler = MainScheduler()


async def start_scheduler():
    await scheduler.start()


async def stop_scheduler():
    await scheduler.stop()