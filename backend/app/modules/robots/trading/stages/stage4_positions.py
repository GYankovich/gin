"""
Stage 4: Управление позициями (открытые, стоп-лосс, тейк-профит)
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone
import logging
from sqlalchemy import text

from app.modules.tinvest.methods.instruments import InstrumentsClient
from app.modules.robots.trading.costs import (
    TradingCosts,
    calculate_stop_loss_price,
    calculate_take_profit_price
)

logger = logging.getLogger(__name__)


class Stage4Positions:
    """Управление позициями"""

    def __init__(self, db, schema: str, token: str, account_id: str, robot_id: int, log_func=None):
        self.db = db
        self.schema = schema
        self.token = token
        self.account_id = account_id
        self.robot_id = robot_id
        self.log_func = log_func
        self.rest_client = InstrumentsClient(token)

    def _write_log(self, message: str):
        """Запись в лог"""
        if self.log_func:
            self.log_func(f"[STAGE4] {message}")
        else:
            logger.info(f"[STAGE4] {message}")

    async def get_open_positions(self) -> List[Dict]:
        """Получает открытые позиции робота из БД"""
        self._write_log("📊 Получение открытых позиций из БД")

        query = """
            SELECT id, figi, side, quantity, entry_price, status
            FROM {}.robot_trades
            WHERE robot_id = :robot_id AND status IN ('open', 'partial')
        """.format(self.schema)

        self._write_log(f"   SQL: {query}")
        self._write_log(f"   robot_id: {self.robot_id}")

        try:
            results = self.db.execute(text(query), {"robot_id": self.robot_id}).fetchall()

            positions = []
            for row in results:
                pos = {
                    "id": row[0],
                    "figi": row[1],
                    "side": row[2],
                    "quantity": float(row[3]) if row[3] else 0,
                    "entry_price": float(row[4]) if row[4] else 0,
                    "status": row[5]
                }
                positions.append(pos)
                self._write_log(f"   {pos['figi']}: {pos['side']} {pos['quantity']} @ {pos['entry_price']:.4f}")

            self._write_log(f"   Итого: {len(positions)} открытых позиций")
            return positions

        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения позиций: {e}")
            return []

    async def check_stop_loss_take_profit(
            self,
            open_positions: List[Dict],
            prices: Dict[str, float],
            risk_params: Dict
    ) -> List[Dict]:
        """Проверяет stop-loss и take-profit для открытых позиций"""
        self._write_log("🔴 Проверка stop-loss/take-profit")

        closed_trades = []
        stop_loss_percent = risk_params.get("stop_loss_percent", 2)
        take_profit_percent = risk_params.get("take_profit_percent", 3)

        for position in open_positions:
            figi = position["figi"]
            entry_price = position["entry_price"]
            current_price = prices.get(figi)
            quantity = position["quantity"]

            if not current_price:
                self._write_log(f"   {figi}: нет текущей цены")
                continue

            stop_loss = calculate_stop_loss_price(entry_price, stop_loss_percent, is_long=True)
            take_profit = calculate_take_profit_price(entry_price, take_profit_percent, is_long=True)

            self._write_log(f"   {figi}: цена={current_price:.4f}, SL={stop_loss:.4f}, TP={take_profit:.4f}")

            should_close = False
            reason = None

            if current_price <= stop_loss:
                should_close = True
                reason = "stop_loss"
                self._write_log(f"      ⚠️ Сработал STOP-LOSS!")
            elif current_price >= take_profit:
                should_close = True
                reason = "take_profit"
                self._write_log(f"      🎯 Сработал TAKE-PROFIT!")

            if should_close:
                try:
                    self._write_log(f"      🔄 Выставление заявки на закрытие...")

                    order = await self.rest_client.post_order(
                        figi=figi,
                        quantity=quantity,
                        price=current_price,
                        direction="ORDER_DIRECTION_SELL",
                        account_id=self.account_id
                    )

                    costs = TradingCosts(entry_price, quantity, is_buy=True)
                    profit_calc = costs.calculate_actual_profit(current_price)

                    await self._close_trade(
                        position["id"],
                        current_price,
                        reason,
                        profit_calc["net_profit"],
                        profit_calc["net_profit_percent"]
                    )

                    closed_trades.append({
                        "trade_id": position["id"],
                        "figi": figi,
                        "exit_price": current_price,
                        "reason": reason,
                        "profit": profit_calc["net_profit"]
                    })

                    self._write_log(f"      ✅ Позиция закрыта. Прибыль: {profit_calc['net_profit']:.2f} руб.")

                except Exception as e:
                    self._write_log(f"      ❌ Ошибка закрытия: {e}")

        self._write_log(f"   Закрыто позиций: {len(closed_trades)}")
        return closed_trades

    async def _close_trade(self, trade_id: int, exit_price: float, reason: str, profit: float, profit_percent: float):
        """Закрывает сделку в БД"""
        query = """
            UPDATE {}.robot_trades
            SET status = 'closed',
                exit_price = :exit_price,
                closed_at = :now,
                profit = :profit,
                profit_percent = :profit_percent
            WHERE id = :trade_id
        """.format(self.schema)

        self.db.execute(
            text(query),
            {
                "trade_id": trade_id,
                "exit_price": exit_price,
                "now": datetime.now(timezone.utc),
                "profit": profit,
                "profit_percent": profit_percent
            }
        )
        self.db.commit()