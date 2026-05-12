#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsPortfolioUpdaterScheduler [1]
#/// Исходный модуль `backend/app/modules/robots/portfolio_updater/scheduler.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/robots/portfolio_updater/scheduler.py
from typing import Dict, Any, List
import asyncio
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging_config import get_logger
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
        for row in results:
            robots.append({
                "robot_id": row[0],
                "user_id": row[1],
                "token_id": row[2],
                "token": row[3]
            })

        return robots

    async def run_update_cycle(self, db: Session) -> Dict[str, Any]:
        """
        Запускает цикл обновления для всех активных роботов
        """
        self.robot.db = db

        results = {
            "total": 0,
            "processed": 0,
            "skipped": 0,
            "errors": []
        }

        # Получаем роботов
        robots = await self.get_robots_for_update(db)
        results["total"] = len(robots)

        if robots:
            system_log.info(f"🔄 Найдено {len(robots)} портфельных роботов для обработки")

        for robot_data in robots:
            try:
                system_log.debug(f"   Запуск робота {robot_data['robot_id']} (user: {robot_data['user_id']})")

                # Запускаем робота
                result = await self.robot.run(
                    robot_id=robot_data["robot_id"],
                    user_id=robot_data["user_id"],
                    token_id=robot_data["token_id"],
                    token=robot_data["token"]
                )

                if result.get("status") == "skipped":
                    results["skipped"] += 1
                    system_log.debug(f"   Робот {robot_data['robot_id']} пропущен: {result.get('reason')}")
                else:
                    results["processed"] += 1
                    accounts = result.get("accounts_found", 0)
                    snapshots = result.get("snapshots_saved", 0)
                    system_log.info(f"   ✅ Робот {robot_data['robot_id']}: {accounts} счетов, {snapshots} снимков")

            except Exception as e:
                error = {
                    "robot_id": robot_data["robot_id"],
                    "user_id": robot_data["user_id"],
                    "token_id": robot_data["token_id"],
                    "error": str(e)
                }
                results["errors"].append(error)
                system_log.error(f"   ❌ Ошибка для робота {robot_data['robot_id']}: {e}")

        if robots:
            system_log.info(
                f"📊 Итоги портфельного обновления: "
                f"всего={results['total']}, "
                f"обработано={results['processed']}, "
                f"пропущено={results['skipped']}, "
                f"ошибок={len(results['errors'])}"
            )

        return results

    async def _run_loop(self):
        """
        Основной цикл планировщика
        """
        system_log.info(f"🔄 Портфельный планировщик запущен (интервал: {self.interval_seconds} сек)")

        while self.running:
            try:
                cycle_start = datetime.now(timezone.utc)
                system_log.debug("Начало цикла обновления портфелей")

                # Создаем сессию БД
                db = SessionLocal()
                try:
                    await self.run_update_cycle(db)
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
                await asyncio.sleep(5)

        system_log.info("🛑 Портфельный планировщик остановлен")

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
            return result
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