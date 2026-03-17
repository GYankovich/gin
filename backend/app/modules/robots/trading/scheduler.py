# app/modules/robots/trading/scheduler.py
from typing import List, Dict, Any
import logging

from sqlalchemy import text

from app.modules.robots.trading.robot import Robot
from app.modules.robots.queries import (
    build_get_active_robots_for_scheduler_query
)

logger = logging.getLogger(__name__)


class TradingScheduler:
    """
    Планировщик для торговых роботов
    """

    def __init__(self):
        self.robots = {}

    async def get_active_trading_robots(self, db) -> List[Dict[str, Any]]:
        """Получает активных торговых роботов"""
        query = """
                SELECT
                    r.id,
                    r.user_id,
                    r.token_id,
                    r.name,
                    r.strategy_name,
                    r.strategy_params,
                    r.account_id,
                    r.max_position_size,
                    r.max_daily_loss,
                    r.max_trades_per_day,
                    t.token
                FROM ganaly.trading_robots r
                         JOIN ganaly.api_tokens t ON r.token_id = t.id
                WHERE r.is_active = 1
                  AND r.status = 'active'
                  AND r.robot_type = 'trading'
                  AND t.is_active = 1 \
                """

        results = db.execute(text(query)).fetchall()

        robots = []
        for row in results:
            robots.append({
                "id": row[0],
                "user_id": row[1],
                "token_id": row[2],
                "name": row[3],
                "strategy_name": row[4],
                "strategy_params": row[5] or {},
                "account_id": row[6],
                "max_position_size": row[7],
                "max_daily_loss": row[8],
                "max_trades_per_day": row[9],
                "token": row[10]
            })

        return robots

    async def run_trading_cycle(self, db) -> Dict[str, Any]:
        """
        Запускает торговый цикл для всех активных роботов
        """
        results = {
            "total": 0,
            "executed": 0,
            "errors": []
        }

        # Получаем активных роботов
        robots = await self.get_active_trading_robots(db)
        results["total"] = len(robots)

        logger.info(f"🔄 Найдено активных торговых роботов: {len(robots)}")

        for robot_data in robots:
            try:
                robot_id = robot_data["id"]

                # Создаём или получаем экземпляр робота
                if robot_id not in self.robots:
                    self.robots[robot_id] = TradingRobot(f"auto_{robot_id}")

                robot = self.robots[robot_id]
                robot.db = db

                # Запускаем робота
                result = await robot.execute(
                    robot_id=robot_id,
                    user_id=robot_data["user_id"],
                    token=robot_data["token"]
                )

                if result.get("status") == "success":
                    results["executed"] += 1

                logger.info(f"✅ Робот {robot_id} выполнен: {result}")

            except Exception as e:
                error = {
                    "robot_id": robot_data["id"],
                    "error": str(e)
                }
                results["errors"].append(error)
                logger.error(f"❌ Ошибка робота {robot_data['id']}: {e}")

        return results