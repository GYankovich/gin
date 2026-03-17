# app/modules/robots/trading/executor.py
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.modules.robots.base.base_robot import BaseRobot
from app.modules.tinvest.methods.clients import create_tbank_client
from app.modules.robots.queries import (
    build_create_trade_query,
    build_update_robot_stats_after_trade_query
)

logger = logging.getLogger(__name__)


class TradeExecutor:
    """
    Исполнитель сделок для торгового робота
    """

    def __init__(self, robot_id: int, db):
        self.robot_id = robot_id
        self.db = db

    def _safe_float(self, value, default: float = 0.0) -> float:
        """Безопасное преобразование в float"""
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    async def check_risk_limits(
            self,
            robot: Dict[str, Any],
            side: str,
            quantity: float,
            price: float
    ) -> tuple[bool, str]:
        """
        Проверка риск-лимитов перед сделкой
        """
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Получаем сегодняшние сделки
        trades_query = """
                       SELECT profit FROM ganaly.robot_trades
                       WHERE robot_id = :robot_id
                         AND created_at >= :today_start
                         AND status = 'closed' \
                       """
        trades = self.db.execute(
            text(trades_query),
            {"robot_id": self.robot_id, "today_start": today_start}
        ).fetchall()

        # Проверка дневного лимита убытков
        if robot.get("max_daily_loss"):
            daily_loss = sum(abs(t[0]) for t in trades if t[0] and t[0] < 0)
            if daily_loss >= robot["max_daily_loss"]:
                return False, f"Daily loss limit reached: {daily_loss:.2f}%"

        # Проверка максимального количества сделок в день
        if robot.get("max_trades_per_day"):
            if len(trades) >= robot["max_trades_per_day"]:
                return False, f"Max trades per day reached: {len(trades)}"

        # Проверка максимального размера позиции
        if robot.get("max_position_size"):
            position_value = quantity * price
            if position_value > robot["max_position_size"]:
                return False, f"Position size {position_value:.2f} exceeds limit {robot['max_position_size']:.2f}"

        return True, "OK"

    async def execute_trade(
            self,
            robot: Dict[str, Any],
            token: str,
            figi: str,
            ticker: Optional[str],
            instrument_type: str,
            side: str,  # 'buy' или 'sell'
            quantity: float,
            price: float,
            account_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Исполнение сделки через T-Invest API
        """
        try:
            # Проверяем лимиты
            ok, message = await self.check_risk_limits(robot, side, quantity, price)
            if not ok:
                logger.warning(f"Trade rejected: {message}")
                return None

            # Создаём клиент T-Invest
            client = create_tbank_client(token)

            # Выставляем ордер
            order = await client.post_order(
                figi=figi,
                quantity=int(quantity),
                price=price,
                direction=f"ORDER_DIRECTION_{side.upper()}",
                account_id=account_id
            )

            if not order:
                logger.error(f"Failed to place order for {figi}")
                return None

            # Сохраняем сделку в БД
            now = datetime.now(timezone.utc)
            total_amount = quantity * price

            insert_query = build_create_trade_query()
            result = self.db.execute(
                text(insert_query),
                {
                    "robot_id": self.robot_id,
                    "figi": figi,
                    "ticker": ticker,
                    "instrument_type": instrument_type,
                    "side": side,
                    "quantity": quantity,
                    "price": price,
                    "total_amount": total_amount,
                    "order_id": order.get("order_id"),
                    "status": "open",
                    "created_at": now
                }
            ).first()

            trade_id = result[0] if result else None

            # Обновляем статистику робота
            update_query = build_update_robot_stats_after_trade_query()
            self.db.execute(
                text(update_query),
                {
                    "robot_id": self.robot_id,
                    "success_increment": 0,
                    "profit": 0,
                    "profit_percent": 0
                }
            )

            self.db.commit()

            logger.info(f"✅ Trade executed: {side} {quantity} {ticker or figi} @ {price}")

            return {
                "trade_id": trade_id,
                "order_id": order.get("order_id"),
                "figi": figi,
                "side": side,
                "quantity": quantity,
                "price": price,
                "total_amount": total_amount,
                "status": "open"
            }

        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            self.db.rollback()
            return None

    async def close_trade(
            self,
            trade_id: int,
            close_price: float
    ) -> Optional[Dict[str, Any]]:
        """
        Закрытие сделки
        """
        try:
            # Получаем информацию о сделке
            trade_query = """
                          SELECT t.*, r.user_id
                          FROM ganaly.robot_trades t
                                   JOIN ganaly.trading_robots r ON t.robot_id = r.id
                          WHERE t.id = :trade_id AND t.status = 'open' \
                          """
            trade = self.db.execute(text(trade_query), {"trade_id": trade_id}).first()

            if not trade:
                logger.warning(f"Trade {trade_id} not found or already closed")
                return None

            # Рассчитываем прибыль
            if trade[5] == "buy":  # side
                profit = (close_price - trade[7]) * trade[6]  # (close_price - price) * quantity
            else:
                profit = (trade[7] - close_price) * trade[6]  # (price - close_price) * quantity

            total_amount = trade[8]  # total_amount
            profit_percent = (profit / total_amount) * 100 if total_amount else 0

            now = datetime.now(timezone.utc)

            # Закрываем сделку
            close_query = """
                          UPDATE ganaly.robot_trades
                          SET status = 'closed',
                              closed_at = :closed_at,
                              exit_price = :exit_price,
                              profit = :profit,
                              profit_percent = :profit_percent
                          WHERE id = :trade_id AND status = 'open'
                              RETURNING id, robot_id, profit, profit_percent \
                          """

            result = self.db.execute(
                text(close_query),
                {
                    "trade_id": trade_id,
                    "closed_at": now,
                    "exit_price": close_price,
                    "profit": profit,
                    "profit_percent": profit_percent
                }
            ).first()

            if not result:
                return None

            robot_id = result[1]

            # Обновляем статистику робота
            update_query = build_update_robot_stats_after_trade_query()
            self.db.execute(
                text(update_query),
                {
                    "robot_id": robot_id,
                    "success_increment": 1 if profit > 0 else 0,
                    "profit": profit,
                    "profit_percent": profit_percent
                }
            )

            self.db.commit()

            logger.info(f"✅ Trade closed: profit {profit:.2f} ({profit_percent:.2f}%)")

            return {
                "trade_id": trade_id,
                "profit": profit,
                "profit_percent": profit_percent,
                "closed_at": now
            }

        except Exception as e:
            logger.error(f"Error closing trade: {e}")
            self.db.rollback()
            return None