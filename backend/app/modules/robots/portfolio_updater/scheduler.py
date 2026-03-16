# app/modules/robots/portfolio_updater/scheduler.py
from typing import List, Dict, Any
import logging

from sqlalchemy import text

from app.modules.robots.portfolio_updater.robot import PortfolioUpdaterRobot
from app.modules.robots.queries import build_get_tokens_for_update_query

logger = logging.getLogger(__name__)


class PortfolioUpdaterScheduler:
    """
    Планировщик для робота обновления портфеля
    """

    def __init__(self):
        self.robot = PortfolioUpdaterRobot("scheduler")

    async def get_tokens_for_update(self, db) -> List[Dict[str, Any]]:
        """Получает токены, которые нужно обновить"""
        query = build_get_tokens_for_update_query()
        results = db.execute(text(query)).fetchall()

        tokens = []
        for row in results:
            tokens.append({
                "id": row[0],
                "user_id": row[1],
                "token": row[2],
                "refresh_interval": row[3] or 60,
                "last_used_at": row[4]
            })

        return tokens

    async def run_update_cycle(self, db) -> Dict[str, Any]:
        """
        Запускает цикл обновления для всех токенов
        """
        self.robot.db = db

        results = {
            "total": 0,
            "processed": 0,
            "skipped": 0,
            "errors": []
        }

        # Получаем токены для обновления
        tokens = await self.get_tokens_for_update(db)
        results["total"] = len(tokens)

        self.robot.log.info(f"🔄 Найдено {len(tokens)} токенов для обработки")

        for token in tokens:
            try:
                # Запускаем робота для каждого токена
                result = await self.robot.run(
                    user_id=token["user_id"],
                    token_id=token["id"],
                    token=token["token"]
                )

                if result.get("status") == "skipped":
                    results["skipped"] += 1
                else:
                    results["processed"] += 1

            except Exception as e:
                error = {
                    "token_id": token["id"],
                    "user_id": token["user_id"],
                    "error": str(e)
                }
                results["errors"].append(error)
                self.robot.log.error(f"❌ Ошибка для токена {token['id']}: {e}")

        self.robot.log.info(f"📊 Итоги: всего={results['total']}, "
                            f"обработано={results['processed']}, "
                            f"пропущено={results['skipped']}, "
                            f"ошибок={len(results['errors'])}")

        return results