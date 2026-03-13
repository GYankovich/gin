from sqlalchemy.orm import Session
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.core.database import SessionLocal
from app.modules.robots.models import TradingRobot, RobotTrade
from app.modules.tinvest.methods.instruments import InstrumentsClient
from app.modules.robots.strategies import get_strategy_class

logger = logging.getLogger(__name__)


class TradingRobotExecutor:
    """
    Исполнитель торгового робота
    """

    def __init__(self, robot_id: int):
        self.robot_id = robot_id
        self.db: Optional[Session] = None
        self.client: Optional[InstrumentsClient] = None
        self.robot: Optional[TradingRobot] = None

    async def __aenter__(self):
        self.db = SessionLocal()
        self.robot = self.db.query(TradingRobot).filter(TradingRobot.id == self.robot_id).first()
        if not self.robot:
            raise ValueError(f"Robot {self.robot_id} not found")

        # Получаем токен
        token = self.db.execute(
            "SELECT token FROM ganaly.api_tokens WHERE id = :id AND is_active = 1",
            {"id": self.robot.token_id}
        ).scalar()
        if not token:
            raise ValueError(f"Token {self.robot.token_id} not found or inactive")

        self.client = InstrumentsClient(token)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.db:
            self.db.close()

    async def check_risk_limits(self) -> bool:
        """
        Проверка дневных лимитов
        """
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        trades_today = self.db.query(RobotTrade).filter(
            RobotTrade.robot_id == self.robot.id,
            RobotTrade.opened_at >= today_start
        ).all()

        # Проверка дневного лимита убытков
        if self.robot.daily_loss_limit:
            daily_loss = sum(t.profit for t in trades_today if t.profit and t.profit < 0)
            if abs(daily_loss) >= self.robot.daily_loss_limit:
                logger.warning(f"Robot {self.robot.id}: daily loss limit reached ({daily_loss})")
                return False

        # Проверка максимального количества сделок в день
        if self.robot.max_trades_per_day and len(trades_today) >= self.robot.max_trades_per_day:
            logger.warning(f"Robot {self.robot.id}: max trades per day reached ({len(trades_today)})")
            return False

        return True

    async def get_account_balance(self) -> float:
        """
        Получить баланс счета (упрощенно - через портфель)
        """
        try:
            # Получаем портфель для определения доступных средств
            portfolio = await self.client.get_portfolio(self.robot.account_id)
            total = portfolio.get('totalAmountPortfolio', {})
            return total.get('units', 0) + total.get('nano', 0) / 1e9
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0.0

    async def get_last_price(self, figi: str) -> float:
        """
        Получить последнюю цену инструмента
        """
        to_date = datetime.utcnow()
        from_date = to_date - timedelta(days=1)
        candles = await self.client.get_candles(figi, from_date, to_date, 'CANDLE_INTERVAL_HOUR')
        if candles:
            last = candles[-1]['close']
            return last.get('units', 0) + last.get('nano', 0) / 1e9
        return 0.0

    async def execute(self):
        """
        Запуск стратегии и исполнение сигналов
        """
        try:
            # Проверяем лимиты
            if not await self.check_risk_limits():
                return

            # Создаем экземпляр стратегии
            strategy_class = get_strategy_class(self.robot.strategy_name)
            strategy = strategy_class(self.client, self.robot.strategy_params or {})

            # Получаем сигналы
            signals = await strategy.generate_signals()
            if not signals:
                logger.info(f"Robot {self.robot.id}: no signals")
                return

            # Получаем баланс
            balance = await self.get_account_balance()
            if balance <= 0:
                logger.warning(f"Robot {self.robot.id}: zero balance")
                return

            # Обрабатываем сигналы
            for figi, direction in signals.items():
                if not direction:
                    continue

                # Получаем текущую цену
                price = await self.get_last_price(figi)
                if price <= 0:
                    continue

                # Рассчитываем размер позиции
                max_position_value = balance * (self.robot.max_position_size_percent / 100.0)
                quantity = int(max_position_value / price)
                if quantity <= 0:
                    continue

                # Выставляем заявку
                try:
                    order = await self.client.post_order(
                        figi=figi,
                        quantity=quantity,
                        price=price,
                        direction=f"ORDER_DIRECTION_{direction}",
                        account_id=self.robot.account_id
                    )

                    # Логируем сделку
                    trade = RobotTrade(
                        robot_id=self.robot.id,
                        figi=figi,
                        direction=direction,
                        quantity=quantity,
                        price=price,
                        total_value=quantity * price,
                        opened_at=datetime.utcnow(),
                        status='OPEN'
                    )
                    self.db.add(trade)

                    # Обновляем статистику робота
                    self.robot.total_trades += 1
                    self.robot.last_run_at = datetime.utcnow()

                    self.db.commit()

                    logger.info(f"Robot {self.robot.id}: {direction} {quantity} {figi} at {price}")

                    # Вызываем колбэк стратегии
                    await strategy.on_order_filled(figi, direction, quantity, price)

                except Exception as e:
                    logger.error(f"Order failed for {figi}: {e}")

        except Exception as e:
            logger.error(f"Robot {self.robot.id} execution error: {e}")