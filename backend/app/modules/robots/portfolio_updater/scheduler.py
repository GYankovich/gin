# app/modules/robots/portfolio_updater/scheduler.py
from typing import Dict, Any, List
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.robots.portfolio_updater.robot import PortfolioUpdaterRobot
from . import queries

logger = logging.getLogger(__name__)


class PortfolioUpdaterScheduler:
    """
    Планировщик для робота обновления портфеля
    """

    def __init__(self):
        self.robot = PortfolioUpdaterRobot("scheduler")
        self.schema = self.robot.schema

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

        self.robot.log.info(f"🔄 Найдено {len(robots)} роботов для обработки")

        for robot_data in robots:
            try:
                # Запускаем робота
                result = await self.robot.run(
                    robot_id=robot_data["robot_id"],
                    user_id=robot_data["user_id"],
                    token_id=robot_data["token_id"],
                    token=robot_data["token"]
                )

                if result.get("status") == "skipped":
                    results["skipped"] += 1
                else:
                    results["processed"] += 1

            except Exception as e:
                error = {
                    "robot_id": robot_data["robot_id"],
                    "user_id": robot_data["user_id"],
                    "token_id": robot_data["token_id"],
                    "error": str(e)
                }
                results["errors"].append(error)
                self.robot.log.error(f"❌ Ошибка для робота {robot_data['robot_id']}: {e}")

        self.robot.log.info(
            f"📊 Итоги: всего={results['total']}, "
            f"обработано={results['processed']}, "
            f"пропущено={results['skipped']}, "
            f"ошибок={len(results['errors'])}"
        )

        return results