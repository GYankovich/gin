"""
Шедулер для торговых роботов - управляет сессиями
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.robots.trading.session import TradingSession
from app.modules.robots.common.logger import get_logger

logger = logging.getLogger(__name__)
system_log = get_logger("SYSTEM", "TRADING_SCHEDULER")


class TradingScheduler:
    """
    Шедулер для торговых роботов
    Запускает сессии для каждого активного робота
    """

    def __init__(self):
        self.running = False
        self.task = None
        self.active_sessions: Dict[int, asyncio.Task] = {}  # robot_id -> task

    async def _get_active_robots(self, db) -> List[Dict]:
        """Получает активных торговых роботов"""
        query = """
                SELECT
                    r.id as robot_id,
                    r.user_id,
                    r.token_id,
                    r.config,
                    at.token as token_value
                FROM ganaly.robots r
                         INNER JOIN ganaly.api_tokens at ON r.token_id = at.id
                WHERE r.type = 2
                  AND r.status = 1
                  AND at.is_active = 1 \
                """
        result = db.execute(text(query)).fetchall()

        robots = []
        for row in result:
            robots.append({
                "robot_id": row[0],
                "user_id": row[1],
                "token_id": row[2],
                "config": row[3] or {},
                "token": row[4]
            })

        return robots

    def _should_start_session(self, robot: Dict) -> bool:
        """
        Проверяет, нужно ли запускать сессию для робота
        По расписанию из robot_schedules
        """
        # TODO: реализовать проверку по расписанию
        return True

    async def _run_session(self, robot: Dict, db):
        """Запускает сессию для одного робота"""
        robot_id = robot["robot_id"]
        system_log.info(f"🤖 Запуск сессии для робота {robot_id}")

        def log_func(msg):
            system_log.info(msg)

        session = None
        try:
            session = TradingSession(
                db=db,
                schema="ganaly",
                robot_id=robot_id,
                user_id=robot["user_id"],
                token_id=robot["token_id"],
                token=robot["token"],
                config=robot["config"],
                log_func=log_func
            )

            result = await session.run()
            system_log.info(f"✅ Сессия робота {robot_id} завершена: {result}")

        except asyncio.CancelledError:
            system_log.info(f"⏹️ Сессия робота {robot_id} отменена")
        except Exception as e:
            system_log.error(f"❌ Ошибка в сессии робота {robot_id}: {e}")
            import traceback
            system_log.error(traceback.format_exc())
        finally:
            if session:
                session.running = False

    async def _run_cycle(self):
        """Один цикл работы шедулера — запускает новые сессии"""
        db = SessionLocal()

        try:
            # Получаем активных роботов
            robots = await self._get_active_robots(db)

            if not robots:
                system_log.debug("Нет активных торговых роботов")
                return

            system_log.info(f"📊 Найдено активных роботов: {len(robots)}")

            # Для каждого робота проверяем, нужно ли запустить сессию
            for robot in robots:
                robot_id = robot["robot_id"]

                # Если сессия уже запущена — пропускаем
                if robot_id in self.active_sessions and not self.active_sessions[robot_id].done():
                    continue

                # Проверяем, нужно ли запускать
                if self._should_start_session(robot):
                    # Создаем новую сессию
                    task = asyncio.create_task(self._run_session(robot, db))
                    self.active_sessions[robot_id] = task

                    # Добавляем колбэк для очистки
                    task.add_done_callback(lambda t, rid=robot_id: self._cleanup_session(rid))

            # Очищаем завершенные сессии
            to_remove = [rid for rid, t in self.active_sessions.items() if t.done()]
            for rid in to_remove:
                del self.active_sessions[rid]

        except Exception as e:
            system_log.error(f"Ошибка в цикле шедулера: {e}")
        finally:
            db.close()

    def _cleanup_session(self, robot_id: int):
        """Очищает завершенную сессию"""
        if robot_id in self.active_sessions:
            del self.active_sessions[robot_id]
            system_log.debug(f"Сессия робота {robot_id} очищена")

    async def _run_loop(self):
        """Основной цикл шедулера"""
        while self.running:
            try:
                await self._run_cycle()
                # Проверяем каждые 30 секунд
                await asyncio.sleep(30)
            except Exception as e:
                system_log.error(f"Ошибка в основном цикле: {e}")
                await asyncio.sleep(5)

    async def start(self):
        """Запуск шедулера"""
        if self.running:
            system_log.warning("Шедулер уже запущен")
            return

        self.running = True
        system_log.info("🚀 Запуск шедулера торговых роботов")
        self.task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Остановка шедулера"""
        self.running = False

        # Отменяем все активные сессии
        for robot_id, task in self.active_sessions.items():
            if not task.done():
                task.cancel()
                system_log.info(f"🛑 Отмена сессии робота {robot_id}")

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        system_log.info("🛑 Шедулер торговых роботов остановлен")

    async def force_run(self, robot_id: int):
        """Принудительный запуск робота"""
        db = SessionLocal()
        try:
            robots = await self._get_active_robots(db)
            robot = next((r for r in robots if r["robot_id"] == robot_id), None)

            if robot:
                return await self._run_session(robot, db)
            else:
                return {"status": "error", "message": f"Robot {robot_id} not found"}
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