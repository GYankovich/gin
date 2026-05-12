#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingStrategiesBase [1]
#/// Исходный модуль `backend/app/modules/robots/trading/strategies/base.py` — автоматическая разметка для Obsidian Source Scanner.

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from app.modules.tinvest.methods.instruments import InstrumentsClient


class BaseStrategy(ABC):
    """
    Базовый класс для всех торговых стратегий
    """

    def __init__(self, client: InstrumentsClient, params: Dict[str, Any]):
        self.client = client
        self.params = params
        self.figis = params.get('figis', [])

    @abstractmethod
    async def generate_signals(self, candles_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Optional[str]]:
        """
        Генерирует сигналы для каждого инструмента

        Args:
            candles_data: Исторические свечи по FIGI в формате {figi: [candles]}

        Returns:
            Dict[str, Optional[str]]: {figi: 'BUY'/'SELL'/None}
        """
        pass

    async def on_order_filled(self, figi: str, direction: str, quantity: int, price: float):
        """
        Вызывается после успешного исполнения заявки
        Можно переопределить в наследниках для трейлинг-стопов и т.д.
        """
        pass

    async def get_required_candles_count(self) -> int:
        """
        Возвращает необходимое количество свечей для расчета
        """
        return 50  # по умолчанию