"""
Stage 6: Выставление заявок
Использует TInvestFacade и PriceParsingMixin
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone

from app.modules.tinvest.facade import TInvestFacade
from app.modules.robots.common.mixins import PriceParsingMixin
from app.modules.robots.trading.costs import TradingCosts
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Stage6Orders(PriceParsingMixin):
    """Выставление заявок через TInvestFacade"""

    def __init__(self, db, schema: str, token: str, account_id: str, robot_id: int, token_id: int, user_id: int, log_func=None):
        self.db = db
        self.schema = schema
        self.token = token
        self.account_id = account_id
        self.robot_id = robot_id
        self.token_id = token_id
        self.user_id = user_id
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
            self.log_func(f"[STAGE6] {message}")
        else:
            logger.info(f"[STAGE6] {message}")

    async def execute_signals(self, signals: List[Dict]) -> List[Dict]:
        """Выставляет заявки на основе сигналов через фасад"""
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

                # Используем фасад для выставления заявки
                order = await self.facade.post_order(
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

    async def update_order_status(self, order_id: str) -> Dict:
        """
        Обновляет статус заявки через фасад
        """
        self._write_log(f"🔄 Проверка статуса заявки {order_id}...")

        try:
            order_state = await self.facade.get_order_state(self.account_id, order_id)

            status = order_state.get("executionReportStatus")
            lots_executed = int(order_state.get("lotsExecuted", 0))
            lots_requested = int(order_state.get("lotsRequested", 0))

            self._write_log(f"   Статус: {status}, исполнено: {lots_executed}/{lots_requested}")

            # Используем parse_price из миксина
            executed_price = self.parse_price(order_state.get("executedOrderPrice"))
            commission = self.parse_price(order_state.get("executedCommission"))

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
                "executed_price": executed_price,
                "commission": commission
            }

        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения статуса: {e}")
            return {"order_id": order_id, "status": "ERROR", "error": str(e)}