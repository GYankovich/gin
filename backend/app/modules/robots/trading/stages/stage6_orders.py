"""
Stage 6: Выставление заявок
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone
import logging
import json

from sqlalchemy import text

from app.modules.tinvest.methods.instruments import InstrumentsClient
from app.modules.robots.trading.costs import TradingCosts

logger = logging.getLogger(__name__)


class Stage6Orders:
    """Выставление заявок"""

    def __init__(self, db, schema: str, token: str, account_id: str, robot_id: int, token_id: int, user_id: int, log_func=None):
        self.db = db
        self.schema = schema
        self.token = token
        self.account_id = account_id
        self.robot_id = robot_id
        self.token_id = token_id
        self.user_id = user_id
        self.log_func = log_func
        self.rest_client = InstrumentsClient(token)

    def _write_log(self, message: str):
        """Запись в лог"""
        if self.log_func:
            self.log_func(f"[STAGE6] {message}")
        else:
            logger.info(f"[STAGE6] {message}")

    async def execute_signals(self, signals: List[Dict]) -> List[Dict]:
        """Выставляет заявки на основе сигналов"""
        self._write_log("📊 Выставление заявок")
        self._write_log(f"   Всего сигналов: {len(signals)}")

        trades = []

        for signal in signals:
            try:
                direction = "ORDER_DIRECTION_BUY" if signal["signal"] == "BUY" else "ORDER_DIRECTION_SELL"

                self._write_log(f"\n   📝 Обработка сигнала: {signal['figi']}")
                self._write_log(f"      Направление: {direction}")
                self._write_log(f"      Количество: {signal['quantity']}")
                self._write_log(f"      Цена: {signal['price']:.4f}")

                api_start = datetime.now(timezone.utc)
                order = await self.rest_client.post_order(
                    figi=signal["figi"],
                    quantity=signal["quantity"],
                    price=signal["price"],
                    direction=direction,
                    account_id=self.account_id
                )

                order_id = order.get("orderId")
                order_status = order.get("executionReportStatus", "NEW")

                costs = TradingCosts(signal["price"], signal["quantity"], is_buy=(signal["signal"] == "BUY"))
                commission = costs.calculate_commission()

                self._write_log(f"      ✅ Заявка отправлена:")
                self._write_log(f"         Order ID: {order_id}")
                self._write_log(f"         Статус: {order_status}")
                self._write_log(f"         Комиссия: {commission:.2f} руб.")

                trades.append({
                    "figi": signal["figi"],
                    "side": signal["signal"].lower(),
                    "quantity": signal["quantity"],
                    "price": signal["price"],
                    "total_amount": signal["quantity"] * signal["price"],
                    "entry_price": signal["price"],
                    "commission": commission,
                    "status": "open" if order_status in ["NEW", "PARTIALLYFILL"] else "pending",
                    "order_id": order_id
                })

            except Exception as e:
                error_msg = str(e)
                self._write_log(f"      ❌ Ошибка выставления заявки: {error_msg}")
                trades.append({
                    "figi": signal["figi"],
                    "side": signal["signal"].lower(),
                    "quantity": signal["quantity"],
                    "price": signal["price"],
                    "total_amount": signal["quantity"] * signal["price"],
                    "status": "failed",
                    "error": error_msg
                })

        self._write_log(f"\n   Итого заявок: {len(trades)}")
        return trades

    async def save_trades(self, robot_id: int, trades: List[Dict]) -> List[int]:
        """Сохраняет сделки в БД"""
        self._write_log("💾 Сохранение сделок в БД")

        if not self.db:
            return []

        trade_ids = []

        for trade in trades:
            query = """
                INSERT INTO {}.robot_trades
                (robot_id, figi, side, quantity, price, total_amount, 
                 entry_price, commission, status, order_id, created_at)
                VALUES
                (:robot_id, :figi, :side, :quantity, :price, :total_amount,
                 :entry_price, :commission, :status, :order_id, :now)
                RETURNING id
            """.format(self.schema)

            result = self.db.execute(
                text(query),
                {
                    "robot_id": robot_id,
                    "figi": trade["figi"],
                    "side": trade["side"],
                    "quantity": trade["quantity"],
                    "price": trade["price"],
                    "total_amount": trade["total_amount"],
                    "entry_price": trade.get("entry_price"),
                    "commission": trade.get("commission"),
                    "status": trade["status"],
                    "order_id": trade.get("order_id"),
                    "now": datetime.now(timezone.utc)
                }
            ).first()

            if result:
                trade_ids.append(result[0])
                self._write_log(f"   Сделка сохранена: ID={result[0]}, {trade['figi']} {trade['side']} {trade['quantity']} @ {trade['price']:.4f}")

        if trade_ids:
            self.db.commit()
            self._write_log(f"   Итого сохранено: {len(trade_ids)} сделок")

        return trade_ids

    async def update_order_status(self, order_id: str) -> Dict:
        """
        Обновляет статус заявки и возвращает актуальную информацию
        """
        self._write_log(f"🔄 Проверка статуса заявки {order_id}...")

        try:
            order_state = await self.rest_client.get_order_state(self.account_id, order_id)

            status = order_state.get("executionReportStatus")
            lots_executed = int(order_state.get("lotsExecuted", 0))
            lots_requested = int(order_state.get("lotsRequested", 0))

            self._write_log(f"   Статус: {status}, исполнено: {lots_executed}/{lots_requested}")

            return {
                "order_id": order_id,
                "status": status,
                "lots_executed": lots_executed,
                "lots_requested": lots_requested,
                "is_filled": status == "EXECUTION_REPORT_STATUS_FILL",
                "is_partial": status == "EXECUTION_REPORT_STATUS_PARTIALLYFILL",
                "is_cancelled": status == "EXECUTION_REPORT_STATUS_CANCELLED",
                "is_rejected": status == "EXECUTION_REPORT_STATUS_REJECTED",
                "trades": order_state.get("stages", []),
                "executed_price": self._parse_price(order_state.get("executedOrderPrice")),
                "commission": self._parse_price(order_state.get("executedCommission"))
            }

        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения статуса: {e}")
            return {"order_id": order_id, "status": "ERROR", "error": str(e)}

    def _parse_price(self, price_data: dict) -> Optional[float]:
        """Парсит цену из units/nano"""
        if not price_data:
            return None
        units = price_data.get("units", 0)
        nano = price_data.get("nano", 0)
        try:
            units = int(units) if units else 0
            nano = int(nano) if nano else 0
        except (TypeError, ValueError):
            return None
        return units + nano / 1e9