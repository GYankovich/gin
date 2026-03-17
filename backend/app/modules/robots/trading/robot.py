# app/modules/robots/trading/robot.py
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import logging

from sqlalchemy import text

from app.modules.robots.base.base_robot import BaseRobot
from app.modules.robots.trading.executor import TradeExecutor
from app.modules.tinvest.methods.clients import create_tbank_client
from app.modules.robots.trading.strategies import get_strategy_class
from app.modules.robots.queries import (
    build_get_token_with_refresh_info_query,
    build_get_robot_by_id_query,
    build_update_robot_heartbeat_query
)

logger = logging.getLogger(__name__)


class Robot(BaseRobot):
    """
    Торговый робот, использующий стратегии из strategies/
    """

    def __init__(self, robot_name: str = "trader"):
        super().__init__(
            robot_type="trading",
            robot_name=robot_name,
            version="1.0.0"
        )
        self.executor: Optional[TradeExecutor] = None
        self.strategy = None
        self.client = None
        self.robot_data: Optional[Dict[str, Any]] = None

    async def _load_robot_config(self, robot_id: int, user_id: int) -> Dict[str, Any]:
        """Загружает конфигурацию робота из БД"""
        query = build_get_robot_by_id_query()
        result = self.db.execute(
            text(query),
            {"robot_id": robot_id, "user_id": user_id}
        ).first()

        if not result:
            raise ValueError(f"Robot {robot_id} not found")

        # Преобразуем в словарь (адаптируй под свою структуру)
        return {
            "id": result[0],
            "user_id": result[1],
            "token_id": result[2],
            "name": result[3],
            "strategy_name": result[4],  # В миграции это поле есть
            "strategy_params": result[5] or {},
            "max_position_size": result[6],
            "max_daily_loss": result[7],
            "max_trades_per_day": result[8],
            "account_id": result[9],  # В миграции это поле есть
            "status": result[10],
            "is_active": result[11]
        }

    async def _update_heartbeat(self, robot_id: int):
        """Обновляет время последнего heartbeat"""
        query = build_update_robot_heartbeat_query()
        self.db.execute(
            text(query),
            {
                "robot_id": robot_id,
                "now": datetime.now(timezone.utc)
            }
        )
        self.db.commit()

    async def _get_current_positions(self, account_id: str, token: str) -> List[Dict]:
        """Получает текущие открытые позиции из T-Invest"""
        try:
            if not self.client:
                self.client = create_tbank_client(token)

            portfolio = await self.client.get_portfolio(account_id)
            positions = []

            for pos in portfolio.get("positions", []):
                if pos.get("quantity", {}).get("units", 0) > 0:
                    positions.append({
                        "figi": pos.get("figi"),
                        "ticker": pos.get("ticker"),
                        "instrument_type": pos.get("instrumentType"),
                        "quantity": pos["quantity"]["units"] + pos["quantity"]["nano"] / 1e9,
                        "current_price": pos.get("currentPrice", {}).get("units", 0) +
                                         pos.get("currentPrice", {}).get("nano", 0) / 1e9,
                        "average_price": pos.get("averagePositionPrice", {}).get("units", 0) +
                                         pos.get("averagePositionPrice", {}).get("nano", 0) / 1e9
                    })

            return positions
        except Exception as e:
            self.log.error(f"Error getting positions: {e}")
            return []

    async def execute(self, robot_id: int, user_id: int, token: str, **kwargs) -> Dict[str, Any]:
        """
        Основная работа торгового робота
        """
        self.log.info(f"🚀 Запуск торгового робота ID={robot_id}")

        # Загружаем конфигурацию робота
        self.robot_data = await self._load_robot_config(robot_id, user_id)

        if not self.robot_data.get("is_active") or self.robot_data.get("status") != "active":
            self.log.info("⏸️ Робот неактивен, пропускаем")
            return {"status": "skipped", "reason": "robot_inactive"}

        # Создаём исполнителя сделок
        self.executor = TradeExecutor(robot_id, self.db)

        # Получаем стратегию
        strategy_name = self.robot_data.get("strategy_name")
        if not strategy_name:
            self.log.error("❌ Стратегия не указана")
            return {"status": "error", "error": "No strategy specified"}

        try:
            strategy_class = get_strategy_class(strategy_name)
        except ValueError:
            self.log.error(f"❌ Неизвестная стратегия: {strategy_name}")
            return {"status": "error", "error": f"Unknown strategy: {strategy_name}"}

        # Создаём клиент T-Invest
        self.client = create_tbank_client(token)

        # Инициализируем стратегию
        self.strategy = strategy_class(
            client=self.client,
            params=self.robot_data.get("strategy_params", {})
        )

        # Получаем сигналы
        self.log.info("📊 Генерация сигналов...")
        signals = await self.strategy.generate_signals()

        if not signals:
            self.log.info("📭 Сигналов нет")
            await self._update_heartbeat(robot_id)
            return {"status": "success", "signals_generated": 0, "trades_executed": 0}

        self.log.info(f"📈 Получено сигналов: {len(signals)}")

        # Получаем текущие позиции
        current_positions = await self._get_current_positions(
            self.robot_data["account_id"],
            token
        )
        positions_by_figi = {p["figi"]: p for p in current_positions}

        # Исполняем сигналы
        trades_executed = 0
        results = []

        for figi, signal in signals.items():
            if not signal:
                continue

            # Проверяем, есть ли уже позиция
            existing = positions_by_figi.get(figi)

            # Логика: если сигнал BUY и нет позиции - покупаем
            if signal == "BUY" and not existing:
                # Получаем текущую цену
                price = await self._get_current_price(figi)
                if not price:
                    continue

                # Рассчитываем количество (упрощённо)
                quantity = 1  # В реальности нужно рассчитывать на основе баланса

                # Исполняем сделку
                result = await self.executor.execute_trade(
                    robot=self.robot_data,
                    token=token,
                    figi=figi,
                    ticker=None,  # Можно получить из кэша
                    instrument_type="share",  # Из кэша
                    side="buy",
                    quantity=quantity,
                    price=price,
                    account_id=self.robot_data["account_id"]
                )

                if result:
                    trades_executed += 1
                    results.append(result)

            # Сигнал SELL и есть позиция - продаём
            elif signal == "SELL" and existing:
                # Закрываем позицию
                result = await self.executor.close_trade(
                    trade_id=existing.get("trade_id"),  # Нужно хранить связь
                    close_price=existing["current_price"]
                )

                if result:
                    trades_executed += 1
                    results.append(result)

        # Обновляем heartbeat
        await self._update_heartbeat(robot_id)

        self.log.info(f"✅ Выполнено сделок: {trades_executed}")

        return {
            "status": "success",
            "signals_generated": len(signals),
            "trades_executed": trades_executed,
            "results": results
        }

    async def _get_current_price(self, figi: str) -> Optional[float]:
        """Получает текущую цену инструмента"""
        try:
            # Можно использовать кэш инструментов
            from datetime import datetime, timedelta
            to_date = datetime.utcnow()
            from_date = to_date - timedelta(days=1)

            candles = await self.client.get_candles(
                figi,
                from_date,
                to_date,
                'CANDLE_INTERVAL_HOUR'
            )

            if candles:
                last = candles[-1]['close']
                return last.get('units', 0) + last.get('nano', 0) / 1e9

            return None
        except Exception as e:
            self.log.error(f"Error getting price for {figi}: {e}")
            return None