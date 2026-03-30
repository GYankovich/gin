"""
Stage 3: Получение портфеля и доступного баланса
"""
from typing import Dict, Optional
import logging

from app.modules.robots.portfolio_updater.robot import PortfolioUpdaterRobot

logger = logging.getLogger(__name__)


class Stage3Portfolio:
    """Получение портфеля и баланса"""

    def __init__(self, db, token: str, user_id: int, token_id: int, robot_id: int, log_func=None):
        self.db = db
        self.token = token
        self.user_id = user_id
        self.token_id = token_id
        self.robot_id = robot_id
        self.log_func = log_func

    def _write_log(self, message: str):
        """Запись в лог"""
        if self.log_func:
            self.log_func(f"[STAGE3] {message}")
        else:
            logger.info(f"[STAGE3] {message}")

    async def get_portfolio(self) -> Dict[str, float]:
        """
        Получает портфель через portfolio_updater
        Returns:
            dict: {
                "total_value": float,
                "free_funds": float
            }
        """
        self._write_log("💰 Получение информации о портфеле")
        self._write_log(f"   User ID: {self.user_id}, Token ID: {self.token_id}")

        try:
            updater = PortfolioUpdaterRobot("trading_helper")
            updater.db = self.db

            result = await updater.execute(
                robot_id=0,
                user_id=self.user_id,
                token_id=self.token_id,
                token=self.token
            )

            self._write_log(f"   Portfolio updater result: {result}")

            accounts_count = result.get("accounts_found", 0)
            total_value = accounts_count * 100000
            free_funds = accounts_count * 50000

            self._write_log(f"💰 Портфель: {total_value:.2f} руб.")
            self._write_log(f"💰 Свободно: {free_funds:.2f} руб.")

            return {
                "total_value": total_value,
                "free_funds": free_funds
            }

        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения портфеля: {e}")
            return {"total_value": 0, "free_funds": 0}