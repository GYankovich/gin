# app/modules/robots/trading/scheduler.py (исправленный)

"""
Шедулер для торговых роботов - управляет сессиями
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.config import settings
from app.core.logging_config import get_logger
from app.modules.robots.trading.session import TradingSession
from app.modules.robots.trading import queries as trading_queries
from app.modules.robots.trading.brokers.global_websocket import global_websocket_manager

system_log = get_logger("robots.trading.scheduler")


class TradingScheduler:
    """Шедулер для торговых роботов"""

    def __init__(self):
        self.running = False
        self.task = None
        self.active_sessions: Dict[int, asyncio.Task] = {}
        self.check_interval = 30

    async def _get_active_robots(self, db) -> List[Dict]:
        """Получает активных торговых роботов"""
        query = trading_queries.build_get_active_trading_robots_query().format(schema=settings.DB_SCHEMA)

        try:
            result = db.execute(
                text(query),
                {"robot_type": 2, "status_active": 1}
            ).fetchall()
        except Exception as e:
            system_log.error(f"Ошибка получения списка роботов: {e}")
            return []

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
        """Проверяет, нужно ли запускать сессию для робота"""
        # TODO: реализовать проверку по расписанию
        return True

    async def _run_session(self, robot: Dict):
        """Запускает сессию для одного робота"""
        robot_id = robot["robot_id"]
        system_log.info(f"🤖 Запуск торговой сессии для робота {robot_id}")

        def log_func(msg):
            system_log.debug(f"[ROBOT_{robot_id}] {msg}")

        session = None
        try:
            session = TradingSession(
                db=None,
                schema=settings.DB_SCHEMA,
                robot_id=robot_id,
                user_id=robot["user_id"],
                token_id=robot["token_id"],
                token=robot["token"],
                config=robot["config"],
                log_func=log_func
            )

            result = await session.run()
            system_log.info(f"✅ Сессия робота {robot_id} завершена: {result.get('status', 'unknown')}")

        except asyncio.CancelledError:
            system_log.info(f"⏹️ Сессия робота {robot_id} отменена")
        except Exception as e:
            system_log.error(f"❌ Ошибка в сессии робота {robot_id}: {e}", exc_info=True)
        finally:
            if session:
                try:
                    session.running = False
                except:
                    pass
            if robot_id in self.active_sessions:
                del self.active_sessions[robot_id]

    async def _run_cycle(self):
        """Один цикл работы шедулера"""
        db = SessionLocal()
        try:
            robots = await self._get_active_robots(db)

            if robots:
                system_log.debug(f"📊 Найдено активных торговых роботов: {len(robots)}")

            for robot in robots:
                robot_id = robot["robot_id"]

                if robot_id in self.active_sessions and not self.active_sessions[robot_id].done():
                    continue

                if self._should_start_session(robot):
                    system_log.info(f"🔄 Создание новой сессии для робота {robot_id}")
                    task = asyncio.create_task(self._run_session(robot))
                    self.active_sessions[robot_id] = task

            to_remove = [rid for rid, t in self.active_sessions.items() if t.done()]
            for rid in to_remove:
                if rid in self.active_sessions:
                    del self.active_sessions[rid]

        except Exception as e:
            system_log.error(f"Ошибка в цикле шедулера: {e}")
        finally:
            db.close()

    async def _run_loop(self):
        """Основной цикл шедулера"""
        system_log.info(f"🔄 Торговый планировщик запущен (интервал: {self.check_interval} сек)")

        while self.running:
            try:
                await self._run_cycle()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_log.error(f"Ошибка в основном цикле: {e}")
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

        for robot_id, task in list(self.active_sessions.items()):
            if not task.done():
                task.cancel()
                system_log.info(f"🛑 Отмена сессии робота {robot_id}")
        if self.active_sessions:
            await asyncio.gather(*self.active_sessions.values(), return_exceptions=True)
            self.active_sessions.clear()

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        await global_websocket_manager.shutdown_all()

        system_log.info("🛑 Торговый планировщик остановлен")

    async def force_run(self, robot_id: int) -> Dict:
        """Принудительный запуск робота"""
        db = SessionLocal()
        try:
            robots = await self._get_active_robots(db)
            robot = next((r for r in robots if r["robot_id"] == robot_id), None)

            if robot:
                system_log.info(f"🔧 Принудительный запуск робота {robot_id}")
                await self._run_session(robot)
                return {"status": "success", "robot_id": robot_id}
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


async def force_run_trading_robot(robot_id: int) -> Dict:
    """Принудительный запуск торгового робота"""
    return await trading_scheduler.force_run(robot_id)