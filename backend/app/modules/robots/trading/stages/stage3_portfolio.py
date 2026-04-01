"""
Stage 3: Получение портфеля и доступного баланса через TInvestFacade
"""
from typing import Dict, Optional

from app.modules.tinvest.facade import TInvestFacade
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Stage3Portfolio:
    """Получение портфеля и баланса через TInvestFacade"""

    def __init__(self, token: str, account_id: str, log_func=None):
        """
        Args:
            token: Токен T-Invest API
            account_id: ID счета для получения портфеля
            log_func: Функция для логирования
        """
        self.token = token
        self.account_id = account_id
        self.log_func = log_func
        self._facade: Optional[TInvestFacade] = None

    @property
    def facade(self) -> TInvestFacade:
        """Ленивая инициализация фасада"""
        if self._facade is None:
            self._facade = TInvestFacade(self.token)
        return self._facade

    def _write_log(self, message: str):
        """Запись в лог"""
        if self.log_func:
            self.log_func(f"[STAGE3] {message}")
        else:
            logger.info(f"[STAGE3] {message}")

    async def get_portfolio(self) -> Dict[str, float]:
        """
        Получает портфель через TInvestFacade

        Returns:
            dict: {
                "total_value": float,  # Общая стоимость портфеля
                "free_funds": float    # Свободные средства
            }
        """
        self._write_log("💰 Получение информации о портфеле")
        self._write_log(f"   Account ID: {self.account_id}")

        try:
            # Получаем портфель через фасад
            portfolio_data = await self.facade.get_portfolio(self.account_id)

            # Извлекаем общую стоимость
            total_amount = portfolio_data.get("total_amount_portfolio", {})
            total_value = total_amount.get("decimal", 0.0) if total_amount else 0.0

            # Получаем свободные средства
            free_funds = await self.facade.get_free_funds(self.account_id)

            self._write_log(f"💰 Портфель: {total_value:.2f} руб.")
            self._write_log(f"💰 Свободно: {free_funds:.2f} руб.")

            return {
                "total_value": total_value,
                "free_funds": free_funds,
                "currency": total_amount.get("currency", "RUB") if total_amount else "RUB"
            }

        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения портфеля: {e}")
            return {"total_value": 0, "free_funds": 0, "currency": "RUB"}

    async def get_portfolio_raw(self) -> Optional[Dict]:
        """
        Получает сырые данные портфеля (для отладки или расширенного использования)

        Returns:
            Полный ответ от API с позициями и деталями
        """
        self._write_log("📊 Получение сырых данных портфеля")

        try:
            portfolio_data = await self.facade.get_portfolio(self.account_id)
            return portfolio_data
        except Exception as e:
            self._write_log(f"   ❌ Ошибка: {e}")
            return None