"""
Stage 6: Выставление заявок
Использует TInvestFacade и PriceParsingMixin
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.common.mixins import PriceParsingMixin
from app.modules.robots.trading.costs import TradingCosts
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class Stage6Orders(PriceParsingMixin):
    """Выставление заявок через TInvestFacade"""

    def __init__(
            self,
            db,
            schema: str,
            broker: BrokerFacade,
            account_id: str,
            robot_id: int,
            token_id: int,
            user_id: int,
            log_func=None,
            daily_trade_counter: Optional[Dict[str, int]] = None,
            last_trade_by_figi: Optional[Dict[str, datetime]] = None,
            cost_params: Optional[Dict[str, float]] = None,
    ):
        self.db = db
        self.schema = schema
        self.broker = broker
        self.account_id = account_id
        self.robot_id = robot_id
        self.token_id = token_id
        self.user_id = user_id
        self.log_func = log_func
        self._daily_trade_counter: Dict[str, int] = daily_trade_counter if daily_trade_counter is not None else {}
        self._last_trade_by_figi: Dict[str, datetime] = last_trade_by_figi if last_trade_by_figi is not None else {}
        self.cost_params: Optional[Dict[str, Any]] = cost_params

    def _cost_kw(self) -> Dict[str, float]:
        if not self.cost_params:
            return {}
        return {
            "broker_commission_rate": float(self.cost_params["broker_commission_rate"]),
            "ndfl_rate": float(self.cost_params["ndfl_rate"]),
        }

    def _write_log(self, message: str):
        """Запись в лог"""
        if self.log_func:
            self.log_func(f"[STAGE6] {message}")
        else:
            logger.info(f"[STAGE6] {message}")

    def _is_near_close(self, risk_params: Dict) -> bool:
        raw = risk_params.get("trading_hours_end", "18:45 MSK")
        hh_mm = raw.split(" ")[0]
        try:
            hh, mm = hh_mm.split(":")
            close_minutes = int(hh) * 60 + int(mm)
        except Exception:
            close_minutes = 18 * 60 + 45
        now_utc = datetime.now(timezone.utc)
        msk_dt = now_utc + timedelta(hours=3)
        msk_minutes = msk_dt.hour * 60 + msk_dt.minute
        return close_minutes - msk_minutes <= 5

    def _is_trading_time_allowed(self, risk_params: Dict) -> bool:
        now_utc = datetime.now(timezone.utc)
        now_msk = now_utc + timedelta(hours=3)

        weekdays_mask = int(risk_params.get("allowed_weekdays", 31))
        # Monday bit=1 ... Friday bit=16
        bit = 1 << min(now_msk.weekday(), 6)
        if (weekdays_mask & bit) == 0:
            return False

        start_raw = risk_params.get("trading_hours_start", "10:00 MSK").split(" ")[0]
        end_raw = risk_params.get("trading_hours_end", "18:45 MSK").split(" ")[0]
        try:
            start_h, start_m = [int(x) for x in start_raw.split(":")]
            end_h, end_m = [int(x) for x in end_raw.split(":")]
        except Exception:
            start_h, start_m = 10, 0
            end_h, end_m = 18, 45

        current = now_msk.hour * 60 + now_msk.minute
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m
        return start <= current <= end

    def _signal_priority(self, signal: Dict) -> int:
        # Lower value means higher priority
        value = str(signal.get("signal", "")).upper()
        if value == "SELL":
            return 3
        if value == "BUY":
            return 4
        if value == "REBALANCE":
            return 5
        return 100

    def _can_trade_signal(self, signal: Dict, risk_params: Dict) -> Optional[str]:
        if not self._is_trading_time_allowed(risk_params):
            return "TRADING_TIME_NOT_ALLOWED"
        if self._is_near_close(risk_params):
            return "TRADING_WINDOW_CLOSED"

        today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        max_deals = int(risk_params.get("max_trades_per_day", 10))
        if self._daily_trade_counter.get(today_key, 0) >= max_deals:
            return "MAX_TRADES_PER_DAY"

        figi = signal["figi"]
        min_seconds = int(risk_params.get("min_seconds_between_trades", 60))
        last_ts = self._last_trade_by_figi.get(figi)
        if last_ts is not None:
            delta = (datetime.now(timezone.utc) - last_ts).total_seconds()
            if delta < min_seconds:
                return "MIN_INTERVAL_BETWEEN_TRADES"

        min_amount = float(risk_params.get("min_trade_amount_rub", 500))
        if signal["quantity"] * signal["price"] < min_amount:
            return "MIN_TRADE_AMOUNT"

        return None

    @staticmethod
    def map_execution_status_to_trade_status(execution_status: str) -> str:
        mapping = {
            "EXECUTION_REPORT_STATUS_NEW": "open",
            "EXECUTION_REPORT_STATUS_PARTIALLYFILL": "partial",
            "EXECUTION_REPORT_STATUS_FILL": "closed",
            "EXECUTION_REPORT_STATUS_CANCELLED": "cancelled",
            "EXECUTION_REPORT_STATUS_REJECTED": "rejected",
        }
        return mapping.get(execution_status, "pending")

    async def execute_signals(self, signals: List[Dict], risk_params: Optional[Dict] = None) -> List[Dict]:
        """Выставляет заявки на основе сигналов через фасад"""
        risk_params = risk_params or {}
        self._write_log("📊 Выставление заявок")
        self._write_log(f"   Всего сигналов: {len(signals)}")

        trades = []
        ordered_signals = sorted(signals, key=self._signal_priority)

        for signal in ordered_signals:
            try:
                if str(signal.get("signal", "")).upper() == "REBALANCE":
                    trades.append({
                        "figi": signal["figi"],
                        "side": "rebalance",
                        "quantity": signal["quantity"],
                        "price": signal["price"],
                        "total_amount": signal["quantity"] * signal["price"],
                        "status": "skipped",
                        "error": "REBALANCE_NO_ORDER",
                        "signal_id": signal.get("_signal_id"),
                    })
                    continue

                reject_reason = self._can_trade_signal(signal, risk_params)
                if reject_reason:
                    self._write_log(f"      ⏭️ Сигнал пропущен: {reject_reason}")
                    trades.append({
                        "figi": signal["figi"],
                        "side": signal["signal"].lower(),
                        "quantity": signal["quantity"],
                        "price": signal["price"],
                        "total_amount": signal["quantity"] * signal["price"],
                        "status": "skipped",
                        "error": reject_reason,
                        "signal_id": signal.get("_signal_id"),
                    })
                    continue

                max_slippage_bps = float(risk_params.get("max_slippage_bps", 0) or 0)
                if max_slippage_bps > 0:
                    market_price = await self.broker.get_last_price(self.user_id, signal["figi"])
                    if market_price and market_price > 0:
                        slippage_bps = abs((signal["price"] - market_price) / market_price) * 10000
                        if slippage_bps > max_slippage_bps:
                            trades.append({
                                "figi": signal["figi"],
                                "side": signal["signal"].lower(),
                                "quantity": signal["quantity"],
                                "price": signal["price"],
                                "total_amount": signal["quantity"] * signal["price"],
                                "status": "skipped",
                                "error": "MAX_SLIPPAGE_EXCEEDED",
                                "signal_id": signal.get("_signal_id"),
                            })
                            self._write_log(
                                f"      ⏭️ Сигнал пропущен: MAX_SLIPPAGE_EXCEEDED "
                                f"({slippage_bps:.2f} bps > {max_slippage_bps:.2f} bps)"
                            )
                            continue

                direction = "ORDER_DIRECTION_BUY" if signal["signal"] == "BUY" else "ORDER_DIRECTION_SELL"

                self._write_log(f"\n   📝 Обработка сигнала: {signal['figi']}")
                self._write_log(f"      Направление: {direction}")
                self._write_log(f"      Количество: {signal['quantity']}")
                self._write_log(f"      Цена: {signal['price']:.4f}")

                api_start = datetime.now(timezone.utc)

                # Используем фасад для выставления заявки
                order = await self.broker.post_order(
                    figi=signal["figi"],
                    quantity=signal["quantity"],
                    price=signal["price"],
                    direction=direction,
                    account_id=self.account_id
                )

                order_id = order.get("orderId")
                order_status = order.get("executionReportStatus", "EXECUTION_REPORT_STATUS_NEW")

                costs = TradingCosts(
                    signal["price"],
                    int(signal["quantity"]),
                    is_buy=(signal["signal"] == "BUY"),
                    **self._cost_kw(),
                )
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
                    "status": self.map_execution_status_to_trade_status(order_status),
                    "execution_status": order_status,
                    "order_id": order_id,
                    "signal_id": signal.get("_signal_id"),
                })
                today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                self._daily_trade_counter[today_key] = self._daily_trade_counter.get(today_key, 0) + 1
                self._last_trade_by_figi[signal["figi"]] = datetime.now(timezone.utc)

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
                    "error": error_msg,
                    "signal_id": signal.get("_signal_id"),
                })

        self._write_log(f"\n   Итого заявок: {len(trades)}")
        return trades

    async def update_order_status(self, order_id: str) -> Dict:
        """
        Обновляет статус заявки через фасад
        """
        self._write_log(f"🔄 Проверка статуса заявки {order_id}...")

        try:
            order_state = await self.broker.get_order_state(self.account_id, order_id)

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