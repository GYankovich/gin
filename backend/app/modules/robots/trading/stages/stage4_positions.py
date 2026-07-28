"""
Stage 4: Управление позициями (открытые позиции + plan SL/TP intents).

Place ордеров не делает — только decision → OrderIntent.
Исполнение: LiveExecutionService / Stage6.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingStagesStage4Positions [1]
#/// Исходный модуль `backend/app/modules/robots/trading/stages/stage4_positions.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Dict, List, Optional, Set
from datetime import datetime, timezone
from sqlalchemy import text

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.contracts import OrderIntent
from app.modules.robots.trading.risk.manager import RiskManager
from app.modules.robots.trading.symbol_guard import SymbolGuard, normalize_figi
from app.modules.robots.trading import queries as trading_queries
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Stage4Positions:
    """Управление позициями: read + plan SL/TP exits (без post_order)."""

    def __init__(
            self,
            db,
            schema: str,
            broker: BrokerFacade,
            account_id: str,
            robot_id: int,
            log_func=None,
            cost_params: Optional[Dict[str, float]] = None,
    ):
        self.db = db
        self.schema = schema
        self.broker = broker
        self.account_id = account_id
        self.robot_id = robot_id
        self.log_func = log_func
        self.cost_params: Optional[Dict[str, float]] = cost_params

    def _cost_kw(self) -> Dict[str, float]:
        if not self.cost_params:
            return {}
        return {
            "broker_commission_rate": float(self.cost_params["broker_commission_rate"]),
            "ndfl_rate": float(self.cost_params["ndfl_rate"]),
        }

    def _write_log(self, message: str):
        if self.log_func:
            self.log_func(f"[STAGE4] {message}")
        else:
            logger.info(f"[STAGE4] {message}")

    async def get_open_positions(self) -> List[Dict]:
        """Получает открытые позиции робота из БД"""
        self._write_log("📊 Получение открытых позиций из БД")

        query = trading_queries.build_get_open_positions_query().format(schema=self.schema)

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
                    "status": row[5],
                    "created_at": row[6] if len(row) > 6 else None,
                }
                positions.append(pos)
                self._write_log(f"   {pos['figi']}: {pos['side']} {pos['quantity']} @ {pos['entry_price']:.4f}")

            self._write_log(f"   Итого: {len(positions)} открытых позиций")
            return positions

        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения позиций: {e}")
            return []

    async def plan_stop_loss_take_profit(
            self,
            open_positions: List[Dict],
            prices: Dict[str, float],
            risk_params: Dict,
            *,
            pending_close_figis: Optional[Set[str]] = None,
            guard: Optional[SymbolGuard] = None,
            account_positions: Optional[Dict[str, float]] = None,
    ) -> List[OrderIntent]:
        """Решает, какие позиции закрыть по SL/TP. Возвращает OrderIntent (без place)."""
        self._write_log("🔴 Планирование stop-loss/take-profit (decision only)")

        symbol_guard = guard or SymbolGuard(
            broker=self.broker,
            account_id=self.account_id,
            log_func=self.log_func,
        )
        pending = {
            normalize_figi(x)
            for x in (pending_close_figis or set())
            if normalize_figi(x)
        }
        pending |= symbol_guard.blocked_figis()
        holdings = None
        if account_positions is not None:
            holdings = {
                normalize_figi(k): float(v or 0)
                for k, v in account_positions.items()
                if normalize_figi(k)
            }

        intents = RiskManager.plan_sl_tp_exit_intents(
            open_positions,
            prices,
            risk_params,
            cost_kw=self._cost_kw(),
            log_func=self._write_log,
        )

        accepted: List[OrderIntent] = []
        for intent in intents:
            figi_key = normalize_figi(intent.figi)
            if figi_key in pending:
                self._write_log(
                    f"      ⏭️ Close уже pending/in-flight для {figi_key} — intent не создаём"
                )
                continue

            if holdings is not None:
                broker_signed = float(holdings.get(figi_key, 0.0) or 0.0)
                # SELL closes long (>0); BUY closes short (<0).
                if intent.side == "SELL":
                    available = max(0.0, broker_signed)
                else:
                    available = abs(min(0.0, broker_signed))
                if available <= 1e-12:
                    self._write_log(
                        f"      ⏭️ Нет позиции на брокере для close {figi_key} "
                        f"(broker_qty={broker_signed:g}, side={intent.side}) — skip"
                    )
                    continue
                if float(intent.quantity or 0) > available + 1e-9:
                    self._write_log(
                        f"      🔧 Close qty {figi_key}: {intent.quantity:g} → broker {available:g}"
                    )
                    intent.quantity = available

            if await symbol_guard.has_active_broker_order(figi_key):
                self._write_log(
                    f"      ⏭️ На брокере уже есть активная заявка по {figi_key} — skip"
                )
                pending.add(figi_key)
                continue
            accepted.append(intent)
            if figi_key:
                pending.add(figi_key)
            self._write_log(
                f"      📋 Intent exit_sl_tp {figi_key} {intent.side} qty={intent.quantity} "
                f"reason={intent.reason}"
            )

        self._write_log(f"   Intents на закрытие: {len(accepted)}")
        return accepted

    async def check_stop_loss_take_profit(
            self,
            open_positions: List[Dict],
            prices: Dict[str, float],
            risk_params: Dict,
            *,
            pending_close_figis: Optional[Set[str]] = None,
            guard: Optional[SymbolGuard] = None,
            account_positions: Optional[Dict[str, float]] = None,
    ) -> List[OrderIntent]:
        """Alias: plan SL/TP intents (no broker place)."""
        return await self.plan_stop_loss_take_profit(
            open_positions,
            prices,
            risk_params,
            pending_close_figis=pending_close_figis,
            guard=guard,
            account_positions=account_positions,
        )

    async def _close_trade(self, trade_id: int, exit_price: float, reason: str, profit: float, profit_percent: float):
        """Закрывает сделку в БД"""
        query = trading_queries.build_close_trade_query().format(schema=self.schema)

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
