"""
Stage 6: Выставление заявок (внутренняя реализация).

Prod-вход: `execution.service.LiveExecutionService` (BRD-ARCH-04 этап 4).
Не вызывать Stage6Orders напрямую из session/robot — только через ExecutionService.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingStagesStage6Orders [1]
#/// Исходный модуль `backend/app/modules/robots/trading/stages/stage6_orders.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timezone, timedelta

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.common.mixins import PriceParsingMixin
from app.modules.robots.trading.contracts import OrderIntent
from app.modules.robots.trading.costs import TradingCosts
from app.modules.robots.trading.account_positions_book import (
    signed_qty,
)
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
            account_positions: Optional[Dict[str, float]] = None,
            in_flight_orders: Optional[Dict[str, str]] = None,
            now_fn: Optional[Callable[[], datetime]] = None,
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
        self._in_flight_orders: Dict[str, str] = in_flight_orders if in_flight_orders is not None else {}
        self.cost_params: Optional[Dict[str, Any]] = cost_params
        # Share the session book by reference — live buys/sells must mutate host state.
        self.account_positions: Dict[str, float] = (
            account_positions if account_positions is not None else {}
        )
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        return self._now_fn()

    def _commission_rate(self, *, is_market: bool = False) -> float:
        if not self.cost_params:
            return 0.0005
        maker = self.cost_params.get("maker_fee_rate")
        taker = self.cost_params.get("taker_fee_rate")
        if is_market:
            return float(taker if taker is not None else self.cost_params.get("broker_commission_rate", 0.0005))
        return float(maker if maker is not None else self.cost_params.get("broker_commission_rate", 0.0005))

    def _cost_kw(self, *, is_market: bool = False) -> Dict[str, float]:
        if not self.cost_params:
            return {}
        return {
            "broker_commission_rate": self._commission_rate(is_market=is_market),
            "ndfl_rate": float(self.cost_params.get("ndfl_rate", 0.13)),
        }

    def _write_log(self, message: str):
        """Запись в лог"""
        if self.log_func:
            self.log_func(f"[STAGE6] {message}")
        else:
            logger.info(f"[STAGE6] {message}")

    def _available_qty(self, figi: str) -> float:
        """Long qty available to sell (non-negative)."""
        return max(0.0, signed_qty(self.account_positions, figi))

    def _broker_signed_qty(self, figi: str) -> float:
        return signed_qty(self.account_positions, figi)

    def _short_qty(self, figi: str) -> float:
        return abs(min(0.0, signed_qty(self.account_positions, figi)))

    def _is_near_close(self, risk_params: Dict) -> bool:
        if not bool(risk_params.get("enforce_session_hours", True)):
            return False
        raw = risk_params.get("trading_hours_end", "18:45 MSK")
        hh_mm = raw.split(" ")[0]
        try:
            hh, mm = hh_mm.split(":")
            close_minutes = int(hh) * 60 + int(mm)
        except Exception:
            close_minutes = 18 * 60 + 45
        now_utc = self._now()
        msk_dt = now_utc + timedelta(hours=3)
        msk_minutes = msk_dt.hour * 60 + msk_dt.minute
        return close_minutes - msk_minutes <= 5

    def _is_trading_time_allowed(self, risk_params: Dict) -> bool:
        # ByBit/crypto: enforce_session_hours=false → always allow.
        if not bool(risk_params.get("enforce_session_hours", True)):
            return True
        now_utc = self._now()
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
        # Lower value means higher priority — protective exits before strategy entries.
        intent_kind = str(signal.get("intent_kind") or signal.get("intent_source") or "").lower()
        if intent_kind in {"exit_sl_tp", "flatten"}:
            return 1
        if intent_kind == "exit_strategy":
            return 2
        value = str(signal.get("signal", "")).upper()
        if value == "SELL":
            return 3
        if value == "BUY":
            return 4
        if value == "REBALANCE":
            return 5
        return 100

    def _can_trade_signal(self, signal: Dict, risk_params: Dict) -> Optional[str]:
        intent_kind = str(signal.get("intent_kind") or signal.get("intent_source") or "").lower()
        is_protective_exit = intent_kind in {"exit_sl_tp", "flatten"}

        # Protective exits (SL/TP/flatten) bypass session-hours / daily trade caps.
        if not is_protective_exit:
            if not self._is_trading_time_allowed(risk_params):
                return "TRADING_TIME_NOT_ALLOWED"
            if self._is_near_close(risk_params):
                return "TRADING_WINDOW_CLOSED"

            today_key = self._now().strftime("%Y-%m-%d")
            max_deals = int(risk_params.get("max_trades_per_day", 10))
            if self._daily_trade_counter.get(today_key, 0) >= max_deals:
                return "MAX_TRADES_PER_DAY"

        figi = signal["figi"]
        figi_key = str(figi or "").upper()
        if figi_key and figi_key in self._in_flight_orders:
            return "ORDER_IN_FLIGHT"

        if not is_protective_exit:
            min_seconds = int(risk_params.get("min_seconds_between_trades", 60))
            last_ts = self._last_trade_by_figi.get(figi)
            if last_ts is not None:
                delta = (self._now() - last_ts).total_seconds()
                if delta < min_seconds:
                    return "MIN_INTERVAL_BETWEEN_TRADES"

            min_amount = float(risk_params.get("min_trade_amount_rub", 500))
            if signal["quantity"] * signal["price"] < min_amount:
                return "MIN_TRADE_AMOUNT"

            # Cheap-alt guard: reject entries below configured min last price.
            min_last = float(risk_params.get("min_last_price") or 0)
            if min_last > 0:
                try:
                    px = float(signal.get("price") or 0)
                except Exception:
                    px = 0.0
                if px > 0 and px < min_last:
                    return "MIN_LAST_PRICE"

            # leverage=0 (non-spot) → no margin trading: block new entries.
            max_leverage = float(risk_params.get("max_leverage", 1.0) or 0.0)
            category = str(
                risk_params.get("instrument_category")
                or risk_params.get("bybit_instrument_category")
                or ""
            ).lower()
            margin_enabled = risk_params.get("margin_enabled")
            if margin_enabled is None:
                margin_enabled = max_leverage > 0 or category == "spot"
            if not margin_enabled and category != "spot":
                return "MARGIN_TRADING_DISABLED"

            buying_power = float(risk_params.get("free_funds", 0) or 0)
            if buying_power > 0 and max_leverage > 0:
                max_notional = buying_power * max_leverage
                if (signal["quantity"] * signal["price"]) > max_notional:
                    return "MAX_LEVERAGE_EXCEEDED"

        return None

    @staticmethod
    def map_execution_status_to_trade_status(execution_status: str, *, closing: bool = False) -> str:
        # Entry FILL = open position; exit FILL (closing=True) = closed.
        # NEW/resting limit stays pending until fill (not conflated with open positions).
        fill_status = "closed" if closing else "open"
        mapping = {
            "EXECUTION_REPORT_STATUS_NEW": "pending",
            "EXECUTION_REPORT_STATUS_PARTIALLYFILL": "partial",
            "EXECUTION_REPORT_STATUS_FILL": fill_status,
            "EXECUTION_REPORT_STATUS_CANCELLED": "cancelled",
            "EXECUTION_REPORT_STATUS_REJECTED": "rejected",
        }
        return mapping.get(execution_status, "pending")

    async def execute_intents(
        self,
        intents: List[OrderIntent],
        risk_params: Optional[Dict] = None,
    ) -> List[Dict]:
        """Place orders from OrderIntent list (single post_order path)."""
        if not intents:
            return []
        signals = [intent.to_stage6_signal() for intent in intents]
        return await self.execute_signals(signals, risk_params=risk_params)

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
                        "intent_source": signal.get("intent_source") or signal.get("intent_kind"),
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
                        "intent_source": signal.get("intent_source") or signal.get("intent_kind"),
                        "trade_id": signal.get("trade_id"),
                        "reason": signal.get("reason"),
                    })
                    continue

                max_slippage_bps = float(risk_params.get("max_slippage_bps", 0) or 0)
                intent_kind = str(signal.get("intent_kind") or signal.get("intent_source") or "").lower()
                if max_slippage_bps > 0 and intent_kind not in {"exit_sl_tp", "flatten"}:
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
                                "intent_source": signal.get("intent_source") or signal.get("intent_kind"),
                            })
                            self._write_log(
                                f"      ⏭️ Сигнал пропущен: MAX_SLIPPAGE_EXCEEDED "
                                f"({slippage_bps:.2f} bps > {max_slippage_bps:.2f} bps)"
                            )
                            continue

                direction = "ORDER_DIRECTION_BUY" if signal["signal"] == "BUY" else "ORDER_DIRECTION_SELL"
                signal_value = str(signal.get("signal", "")).upper()
                reduce_only = bool(signal.get("reduce_only")) or intent_kind in {
                    "exit_sl_tp", "flatten",
                }
                figi_key = str(signal.get("figi") or "").upper()
                requested = float(signal.get("quantity") or 0)
                allow_short = bool(risk_params.get("allow_short", False))

                # Never sell what we don't hold; never reduce-only close a flat symbol.
                if signal_value == "SELL":
                    long_qty = self._available_qty(signal["figi"])
                    if reduce_only or not allow_short:
                        if long_qty <= 1e-12:
                            trades.append({
                                "figi": signal["figi"],
                                "side": "sell",
                                "quantity": signal["quantity"],
                                "price": signal["price"],
                                "total_amount": requested * float(signal.get("price") or 0),
                                "status": "skipped",
                                "error": "NO_ASSET_FOR_SELL",
                                "signal_id": signal.get("_signal_id"),
                                "intent_source": signal.get("intent_source") or signal.get("intent_kind"),
                                "trade_id": signal.get("trade_id"),
                                "reason": signal.get("reason"),
                            })
                            self._write_log(
                                f"      ⏭️ SELL пропущен: нет лонга на счете "
                                f"(доступно={long_qty:.4f}, требуется={requested:.4f})"
                            )
                            continue
                        if requested > long_qty + 1e-9:
                            signal = dict(signal)
                            signal["quantity"] = long_qty
                            self._write_log(
                                f"      🔧 SELL qty урезан до брокера: {requested:g} → {long_qty:g}"
                            )
                            requested = long_qty
                elif signal_value == "BUY" and reduce_only:
                    short_qty = self._short_qty(signal["figi"])
                    if short_qty <= 1e-12:
                        trades.append({
                            "figi": signal["figi"],
                            "side": "buy",
                            "quantity": signal["quantity"],
                            "price": signal["price"],
                            "total_amount": requested * float(signal.get("price") or 0),
                            "status": "skipped",
                            "error": "NO_POSITION_TO_CLOSE",
                            "signal_id": signal.get("_signal_id"),
                            "intent_source": signal.get("intent_source") or signal.get("intent_kind"),
                            "trade_id": signal.get("trade_id"),
                            "reason": signal.get("reason"),
                        })
                        self._write_log(
                            f"      ⏭️ BUY reduceOnly пропущен: нет шорта на счете "
                            f"(short={short_qty:.4f}, требуется={requested:.4f})"
                        )
                        continue
                    if requested > short_qty + 1e-9:
                        signal = dict(signal)
                        signal["quantity"] = short_qty
                        self._write_log(
                            f"      🔧 BUY close qty урезан до брокера: {requested:g} → {short_qty:g}"
                        )
                        requested = short_qty

                self._write_log(f"\n   📝 Обработка сигнала: {signal['figi']}")
                self._write_log(f"      Направление: {direction}")
                self._write_log(f"      Количество: {signal['quantity']}")
                self._write_log(f"      Цена: {signal['price']:.4f}")
                if reduce_only:
                    self._write_log("      reduceOnly=True")

                use_market = (
                    getattr(self.broker, "broker_type", "") == "sim_backtest"
                    and str((self.cost_params or {}).get("backtest_execution") or "").lower() == "market_taker"
                )
                if use_market:
                    order = await self.broker.post_market_order(
                        figi=signal["figi"],
                        quantity=signal["quantity"],
                        direction=direction,
                        account_id=self.account_id,
                    )
                else:
                    order = await self.broker.post_order(
                        figi=signal["figi"],
                        quantity=signal["quantity"],
                        price=signal["price"],
                        direction=direction,
                        account_id=self.account_id,
                        reduce_only=reduce_only,
                    )

                order_id = order.get("orderId")
                order_status = order.get("executionReportStatus", "EXECUTION_REPORT_STATUS_NEW")
                closing = reduce_only or intent_kind in {"exit_sl_tp", "flatten", "exit_strategy"}

                costs = TradingCosts(
                    signal["price"],
                    float(signal["quantity"]),
                    is_buy=(signal["signal"] == "BUY"),
                    **self._cost_kw(is_market=use_market),
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
                    "exit_price": signal["price"] if closing else None,
                    "commission": commission,
                    "status": self.map_execution_status_to_trade_status(order_status, closing=closing),
                    "execution_status": order_status,
                    "order_id": order_id,
                    "signal_id": signal.get("_signal_id"),
                    "intent_source": signal.get("intent_source") or signal.get("intent_kind") or (
                        "exit_sl_tp" if reduce_only else "entry"
                    ),
                    "trade_id": signal.get("trade_id"),
                    "reason": signal.get("reason"),
                    "profit": signal.get("estimated_profit"),
                    "reduce_only": reduce_only,
                })
                today_key = self._now().strftime("%Y-%m-%d")
                self._daily_trade_counter[today_key] = self._daily_trade_counter.get(today_key, 0) + 1
                self._last_trade_by_figi[signal["figi"]] = self._now()
                if order_id:
                    self._in_flight_orders[str(signal["figi"]).upper()] = str(order_id)
                # Book updates on FILL only (session poll) — place must not mutate account_positions.
                self._write_log(
                    f"      📦 account_positions wait FILL "
                    f"{str(signal['figi']).upper()} {signal_value} qty={float(signal['quantity'] or 0):g} "
                    f"(book={signed_qty(self.account_positions, signal['figi']):g})"
                )

            except Exception as e:
                error_msg = str(e)
                self._write_log(f"      ❌ Ошибка выставления заявки: {error_msg}")
                from app.modules.robots.trading.broker_position_sync import is_fatal_broker_error

                fatal = is_fatal_broker_error(e)
                trades.append({
                    "figi": signal["figi"],
                    "side": str(signal.get("signal", "")).lower(),
                    "quantity": signal.get("quantity"),
                    "price": signal.get("price"),
                    "total_amount": (signal.get("quantity") or 0) * (signal.get("price") or 0),
                    "status": "failed",
                    "error": error_msg,
                    "fatal_broker_error": fatal,
                    "signal_id": signal.get("_signal_id"),
                    "intent_source": signal.get("intent_source") or signal.get("intent_kind"),
                    "trade_id": signal.get("trade_id"),
                    "reason": signal.get("reason"),
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
            try:
                lots_executed = float(order_state.get("lotsExecuted") or 0)
            except Exception:
                lots_executed = 0.0
            try:
                lots_requested = float(order_state.get("lotsRequested") or 0)
            except Exception:
                lots_requested = 0.0

            self._write_log(f"   Статус: {status}, исполнено: {lots_executed:g}/{lots_requested:g}")

            # Используем parse_price из миксина
            executed_price = self.parse_price(order_state.get("executedOrderPrice"))
            commission = self.parse_price(order_state.get("executedCommission"))
            side_raw = order_state.get("side") or order_state.get("direction")
            figi_raw = order_state.get("symbol") or order_state.get("figi")

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
                "commission": commission,
                "side": side_raw,
                "figi": figi_raw,
            }

        except Exception as e:
            self._write_log(f"   ❌ Ошибка получения статуса: {e}")
            return {"order_id": order_id, "status": "ERROR", "error": str(e)}