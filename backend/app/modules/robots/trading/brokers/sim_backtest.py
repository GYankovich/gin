"""In-memory broker facade for history backtest (full TradingSession replay)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.brokers.margin import (
    initial_margin,
    is_liquidated_long,
    liquidation_price_long,
    resolve_margin_params,
)
from app.modules.robots.trading.costs import TradingCosts
from app.modules.robots.trading.intervals import bar_duration_seconds, resolve_strategy_interval


def _close_price(candle: Dict[str, Any]) -> float:
    cl = candle.get("close") or {}
    if isinstance(cl, (int, float)):
        return float(cl)
    return float(int(cl.get("units", 0) or 0)) + float(int(cl.get("nano", 0) or 0)) / 1e9


def _candle_time_iso(candle: Dict[str, Any]) -> str:
    t = candle.get("time")
    if isinstance(t, str):
        return t
    if isinstance(t, dict):
        return str(t.get("seconds", ""))
    return ""


def _qty_dict(qty: float) -> Dict[str, Any]:
    return {"decimal": float(qty), "units": int(qty), "nano": 0}


class SimBacktestBrokerFacade(BrokerFacade):
    """Virtual broker: historical candles + immediate limit fills."""

    broker_type = "sim_backtest"

    def __init__(
        self,
        *,
        initial_capital: float,
        candles_by_figi: Dict[str, List[Dict[str, Any]]],
        commission_rate: float = 0.0005,
        maker_fee_rate: float | None = None,
        taker_fee_rate: float | None = None,
        ndfl_rate: float = 0.13,
        price_at_bar: Optional[Callable[[str], Optional[float]]] = None,
        leverage: float = 1.0,
        maintenance_margin_rate: float = 0.005,
        margin_enabled: bool = False,
        backtest_fee_model: str = "maker_taker",
        robot_config: Optional[Dict[str, Any]] = None,
    ):
        margin = resolve_margin_params(robot_config) if robot_config else {
            "enabled": margin_enabled,
            "leverage": leverage,
            "maintenance_margin_rate": maintenance_margin_rate,
        }
        self.leverage = float(margin.get("leverage") or leverage or 1.0)
        self.maintenance_margin_rate = float(margin.get("maintenance_margin_rate") or maintenance_margin_rate)
        self.margin_enabled = bool(margin.get("enabled")) if robot_config else bool(margin_enabled)
        self.backtest_fee_model = str(backtest_fee_model or "maker_taker").lower()
        exec_cfg = dict((robot_config or {}).get("execution_model") or {})
        self.slippage_pct = max(0.0, float(exec_cfg.get("slippage_pct") or 0.0))
        latency_sec = max(0.0, float(exec_cfg.get("latency_sec") or 0.0))
        self.latency_bars = 0
        if latency_sec > 0 and robot_config:
            sp = dict(robot_config.get("strategy_params") or {})
            resolved = resolve_strategy_interval(str(sp.get("interval") or "CANDLE_INTERVAL_5_MIN"))
            bar_sec = max(1, int(bar_duration_seconds(resolved.code_num)))
            self.latency_bars = int(math.ceil(latency_sec / bar_sec))
        self.cash = float(initial_capital)
        self.holdings: Dict[str, Dict[str, float]] = {}
        self.candles_by_figi = candles_by_figi
        self.commission_rate = float(commission_rate)
        self.maker_fee_rate = float(maker_fee_rate) if maker_fee_rate is not None else float(commission_rate)
        self.taker_fee_rate = float(taker_fee_rate) if taker_fee_rate is not None else float(commission_rate)
        self.ndfl_rate = float(ndfl_rate)
        self._price_at_bar = price_at_bar
        self._last_prices: Dict[str, float] = {}
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._order_seq = 0
        self.trade_log: List[Dict[str, Any]] = []
        self.funding_log: List[Dict[str, Any]] = []
        self.liquidation_log: List[Dict[str, Any]] = []
        self.current_bar_time: str = ""

    def _apply_slippage(self, px: float, *, is_buy: bool) -> float:
        if px <= 0 or self.slippage_pct <= 0:
            return px
        if is_buy:
            return px * (1.0 + self.slippage_pct / 100.0)
        return px * (1.0 - self.slippage_pct / 100.0)

    def _latency_shifted_price(self, figi: str, base_px: float, *, is_buy: bool) -> float:
        px = float(base_px or 0)
        if self.latency_bars <= 0 or px <= 0:
            return self._apply_slippage(px, is_buy=is_buy)
        f = str(figi or "").upper()
        series = list(self.candles_by_figi.get(f) or self.candles_by_figi.get(figi) or [])
        if not series or not self.current_bar_time:
            return self._apply_slippage(px, is_buy=is_buy)
        idx = None
        for i, c in enumerate(series):
            if _candle_time_iso(c) == self.current_bar_time:
                idx = i
                break
        if idx is None:
            return self._apply_slippage(px, is_buy=is_buy)
        target = idx + self.latency_bars
        if target >= len(series):
            return self._apply_slippage(px, is_buy=is_buy)
        delayed_px = _close_price(series[target])
        if delayed_px <= 0:
            return self._apply_slippage(px, is_buy=is_buy)
        return self._apply_slippage(delayed_px, is_buy=is_buy)

    def _fee_rate(self, *, is_market: bool) -> float:
        if self.backtest_fee_model == "taker_only":
            return self.taker_fee_rate
        if self.backtest_fee_model == "maker_only":
            return self.maker_fee_rate
        return self.taker_fee_rate if is_market else self.maker_fee_rate

    def _effective_ndfl_rate(self) -> float:
        return max(0.0, float(self.ndfl_rate))

    def _calc_realized_pnl(
        self,
        *,
        entry_avg: float,
        exit_px: float,
        qty: int,
        entry_fee_rate: float,
        exit_fee_rate: float,
    ) -> float:
        buy_amount = entry_avg * qty
        sell_amount = exit_px * qty
        commission_buy = buy_amount * entry_fee_rate
        commission_sell = sell_amount * exit_fee_rate
        gross = sell_amount - buy_amount - commission_buy - commission_sell
        tax_rate = self._effective_ndfl_rate()
        if gross > 0 and tax_rate > 0:
            return gross - gross * tax_rate
        return gross

    def _update_holding_buy(self, f: str, qty: int, px: float, fee_rate: float, *, margin_add: float = 0.0) -> None:
        h = self.holdings.setdefault(
            f,
            {"qty": 0.0, "avg_price": 0.0, "avg_entry_fee_rate": fee_rate, "margin_locked": 0.0},
        )
        old_qty = float(h["qty"])
        new_qty = old_qty + qty
        if new_qty > 0:
            h["avg_price"] = (old_qty * float(h["avg_price"]) + qty * px) / new_qty
            prev_fee = float(h.get("avg_entry_fee_rate") or fee_rate)
            h["avg_entry_fee_rate"] = (old_qty * prev_fee + qty * fee_rate) / new_qty
        h["qty"] = new_qty
        if margin_add > 0:
            h["margin_locked"] = float(h.get("margin_locked") or 0) + float(margin_add)

    def fee_totals(self) -> Dict[str, float]:
        maker = sum(float(t.get("commission") or 0) for t in self.trade_log if t.get("fee_kind") == "maker")
        taker = sum(float(t.get("commission") or 0) for t in self.trade_log if t.get("fee_kind") == "taker")
        funding_paid = sum(
            -float(x.get("cash_adjustment") or 0)
            for x in self.funding_log
            if float(x.get("cash_adjustment") or 0) < 0
        )
        funding_received = sum(
            float(x.get("cash_adjustment") or 0)
            for x in self.funding_log
            if float(x.get("cash_adjustment") or 0) > 0
        )
        return {
            "maker_commission": maker,
            "taker_commission": taker,
            "total_commission": maker + taker,
            "funding_paid": funding_paid,
            "funding_received": funding_received,
            "total_funding": funding_paid - funding_received,
        }

    @property
    def cache_namespace(self) -> str:
        return "sim_backtest"

    @property
    def auth_token(self) -> str:
        return "sim"

    def set_last_price(self, figi: str, price: float) -> None:
        if figi and price > 0:
            self._last_prices[str(figi).upper()] = float(price)

    def _mark_price(self, figi: str) -> float:
        f = str(figi or "").upper()
        if self._price_at_bar:
            px = self._price_at_bar(f)
            if px and px > 0:
                return float(px)
        return float(self._last_prices.get(f, 0) or 0)

    def _equity(self) -> float:
        eq = self.cash
        for figi, h in self.holdings.items():
            qty = float(h.get("qty") or 0)
            if qty <= 0:
                continue
            px = self._mark_price(figi)
            entry = float(h.get("avg_price") or 0)
            if px <= 0:
                continue
            if self.margin_enabled:
                margin_locked = float(h.get("margin_locked") or 0)
                eq += margin_locked + qty * (px - entry)
            else:
                eq += qty * px
        return eq

    def margin_summary(self) -> Dict[str, Any]:
        positions: List[Dict[str, Any]] = []
        for figi, h in self.holdings.items():
            qty = float(h.get("qty") or 0)
            if qty <= 0:
                continue
            entry = float(h.get("avg_price") or 0)
            mark = self._mark_price(figi)
            margin_locked = float(h.get("margin_locked") or 0)
            liq = (
                liquidation_price_long(entry, self.leverage, self.maintenance_margin_rate)
                if self.margin_enabled and entry > 0
                else None
            )
            positions.append(
                {
                    "symbol": figi,
                    "qty": qty,
                    "entry_price": entry,
                    "mark_price": mark,
                    "margin_locked": margin_locked,
                    "liquidation_price": liq,
                }
            )
        return {
            "enabled": self.margin_enabled,
            "leverage": self.leverage,
            "maintenance_margin_rate": self.maintenance_margin_rate,
            "liquidations": len(self.liquidation_log),
            "positions": positions,
        }

    def check_liquidations(self) -> List[Dict[str, Any]]:
        if not self.margin_enabled:
            return []
        events: List[Dict[str, Any]] = []
        for figi, h in list(self.holdings.items()):
            qty = int(float(h.get("qty") or 0))
            if qty <= 0:
                continue
            entry = float(h.get("avg_price") or 0)
            mark = self._mark_price(figi)
            if entry <= 0 or mark <= 0:
                continue
            if not is_liquidated_long(mark, entry, self.leverage, self.maintenance_margin_rate):
                continue
            try:
                self._fill_sell(figi, qty, mark, self.taker_fee_rate, liquidation=True)
                ev = {
                    "figi": figi,
                    "qty": qty,
                    "entry_price": entry,
                    "liquidation_price": liquidation_price_long(
                        entry, self.leverage, self.maintenance_margin_rate
                    ),
                    "mark_price": mark,
                    "bar_time": self.current_bar_time,
                }
                self.liquidation_log.append(ev)
                events.append(ev)
            except Exception:
                continue
        return events

    def _fill_buy(self, f: str, qty: int, px: float, fee_rate: float) -> float:
        tc = TradingCosts(px, qty, is_buy=True, broker_commission_rate=fee_rate, ndfl_rate=self._effective_ndfl_rate())
        commission = float(tc.calculate_commission())
        notional = px * qty
        if self.margin_enabled:
            im = initial_margin(notional, self.leverage)
            cost = im + commission
            if cost > self.cash + 1e-6:
                raise ValueError("insufficient margin")
            self.cash -= cost
            self._update_holding_buy(f, qty, px, fee_rate, margin_add=im)
        else:
            cost = notional + commission
            if cost > self.cash + 1e-6:
                raise ValueError("insufficient cash")
            self.cash -= cost
            self._update_holding_buy(f, qty, px, fee_rate)
        return commission

    def _fill_sell(
        self,
        f: str,
        qty: int,
        px: float,
        fee_rate: float,
        *,
        liquidation: bool = False,
    ) -> tuple[float, Optional[float]]:
        h = self.holdings.get(f) or {"qty": 0.0, "avg_price": 0.0, "margin_locked": 0.0}
        total_qty = float(h.get("qty") or 0)
        if total_qty < qty - 1e-9:
            raise ValueError("insufficient position")
        entry_avg = float(h.get("avg_price") or 0)
        entry_fee_rate = float(h.get("avg_entry_fee_rate") or fee_rate)
        tc = TradingCosts(px, qty, is_buy=False, broker_commission_rate=fee_rate, ndfl_rate=self._effective_ndfl_rate())
        commission = float(tc.calculate_commission())
        if self.margin_enabled:
            margin_locked = float(h.get("margin_locked") or 0)
            margin_release = margin_locked * (qty / total_qty) if total_qty > 0 else 0.0
            upl = (px - entry_avg) * qty
            self.cash += margin_release + upl - commission
            h["qty"] = total_qty - qty
            h["margin_locked"] = max(0.0, margin_locked - margin_release)
            if h["qty"] <= 1e-9:
                self.holdings.pop(f, None)
            else:
                self.holdings[f] = h
        else:
            proceeds = px * qty - commission
            self.cash += proceeds
            h["qty"] = total_qty - qty
            if h["qty"] <= 1e-9:
                self.holdings.pop(f, None)
            else:
                self.holdings[f] = h
        pnl_net = None
        if entry_avg > 0:
            pnl_net = self._calc_realized_pnl(
                entry_avg=entry_avg,
                exit_px=px,
                qty=qty,
                entry_fee_rate=entry_fee_rate,
                exit_fee_rate=fee_rate,
            )
        return commission, pnl_net

    def apply_funding_charge(
        self,
        symbol: str,
        funding_rate: float,
        *,
        side: str = "long",
        bar_time: str = "",
    ) -> float:
        """
        Apply ByBit-style funding to open position notional.

        Long pays when rate > 0: cash adjustment = -notional * rate.
        Returns cash adjustment (negative = paid).
        """
        f = str(symbol or "").upper()
        qty = float((self.holdings.get(f) or {}).get("qty") or 0)
        if qty <= 0:
            return 0.0
        px = self._mark_price(f)
        if px <= 0:
            return 0.0
        notional = qty * px
        direction = -1.0 if str(side or "long").lower() != "short" else 1.0
        adjustment = notional * float(funding_rate) * direction
        self.cash += adjustment
        entry = {
            "figi": f,
            "funding_rate": float(funding_rate),
            "notional": notional,
            "cash_adjustment": adjustment,
            "bar_time": bar_time or self.current_bar_time,
            "side": side,
        }
        self.funding_log.append(entry)
        return adjustment

    def open_positions_for_session(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        pos_id = 1
        for figi, h in sorted(self.holdings.items()):
            qty = float(h.get("qty") or 0)
            if qty <= 0:
                continue
            out.append(
                {
                    "id": pos_id,
                    "figi": figi,
                    "side": "buy",
                    "quantity": qty,
                    "entry_price": float(h.get("avg_price") or 0),
                    "status": "open",
                }
            )
            pos_id += 1
        return out

    async def get_accounts(self) -> List[Dict[str, Any]]:
        return [{"id": "BACKTEST", "status": "open", "type": "broker"}]

    async def get_portfolio(self, account_id: str) -> Dict[str, Any]:
        positions: List[Dict[str, Any]] = []
        for figi, h in self.holdings.items():
            qty = float(h.get("qty") or 0)
            if qty <= 0:
                continue
            positions.append(
                {
                    "figi": figi,
                    "ticker": figi,
                    "instrument_type": "share",
                    "quantity": _qty_dict(qty),
                    "average_position_price": _qty_dict(float(h.get("avg_price") or 0)),
                }
            )
        return {
            "total_amount_portfolio": {"decimal": self._equity(), "currency": "RUB"},
            "positions": positions,
        }

    async def get_free_funds(self, account_id: str) -> float:
        return float(self.cash)

    async def get_candles(
        self,
        figi: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
    ) -> List[Dict[str, Any]]:
        series = list(self.candles_by_figi.get(figi) or self.candles_by_figi.get(str(figi).upper()) or [])
        if not series:
            return []
        out: List[Dict[str, Any]] = []
        for c in series:
            iso = _candle_time_iso(c)
            if not iso:
                continue
            try:
                s = iso.replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if from_date <= dt <= to_date:
                out.append(c)
        return out

    async def post_order(
        self,
        figi: str,
        quantity: int,
        price: float,
        direction: str,
        account_id: str,
    ) -> Dict[str, Any]:
        qty = int(quantity or 0)
        px = float(price or 0)
        if qty <= 0 or px <= 0:
            raise ValueError("invalid order qty/price")
        is_buy = "BUY" in str(direction or "").upper()
        f = str(figi or "").upper()
        px = self._latency_shifted_price(f, px, is_buy=is_buy)
        fee_rate = self._fee_rate(is_market=False)
        pnl_net = None
        if is_buy:
            commission = self._fill_buy(f, qty, px, fee_rate)
        else:
            commission, pnl_net = self._fill_sell(f, qty, px, fee_rate)

        self._order_seq += 1
        order_id = f"SIM-{self._order_seq}-{uuid4().hex[:8]}"
        state = {
            "orderId": order_id,
            "executionReportStatus": "EXECUTION_REPORT_STATUS_FILL",
            "lotsExecuted": qty,
            "lotsRequested": qty,
            "executedOrderPrice": {"units": int(px), "nano": int((px % 1) * 1e9)},
            "executedCommission": {"units": int(commission), "nano": int((commission % 1) * 1e9)},
        }
        self._orders[order_id] = state
        self.trade_log.append(
            {
                "order_id": order_id,
                "figi": f,
                "side": "buy" if is_buy else "sell",
                "quantity": qty,
                "price": px,
                "commission": commission,
                "fee_kind": "maker" if fee_rate == self.maker_fee_rate else "taker",
                "order_type": "limit",
                "pnl_net": pnl_net,
                "bar_time": self.current_bar_time,
            }
        )
        return state

    async def get_order_state(self, account_id: str, order_id: str) -> Dict[str, Any]:
        return dict(self._orders.get(order_id) or {"executionReportStatus": "EXECUTION_REPORT_STATUS_REJECTED"})

    async def post_market_order(
        self,
        figi: str,
        quantity: int,
        direction: str,
        account_id: str,
    ) -> Dict[str, Any]:
        px = self._mark_price(str(figi or "").upper())
        if px <= 0:
            raise ValueError("no market price")
        qty = int(quantity or 0)
        if qty <= 0:
            raise ValueError("invalid market order qty")
        is_buy = "BUY" in str(direction or "").upper()
        f = str(figi or "").upper()
        px = self._latency_shifted_price(f, px, is_buy=is_buy)
        fee_rate = self._fee_rate(is_market=True)
        pnl_net = None
        if is_buy:
            commission = self._fill_buy(f, qty, px, fee_rate)
        else:
            commission, pnl_net = self._fill_sell(f, qty, px, fee_rate)

        self._order_seq += 1
        order_id = f"SIM-{self._order_seq}-{uuid4().hex[:8]}"
        state = {
            "orderId": order_id,
            "executionReportStatus": "EXECUTION_REPORT_STATUS_FILL",
            "lotsExecuted": qty,
            "lotsRequested": qty,
            "executedOrderPrice": {"units": int(px), "nano": int((px % 1) * 1e9)},
            "executedCommission": {"units": int(commission), "nano": int((commission % 1) * 1e9)},
        }
        self._orders[order_id] = state
        self.trade_log.append(
            {
                "order_id": order_id,
                "figi": f,
                "side": "buy" if is_buy else "sell",
                "quantity": qty,
                "price": px,
                "commission": commission,
                "fee_kind": "maker" if fee_rate == self.maker_fee_rate else "taker",
                "order_type": "market",
                "pnl_net": pnl_net,
                "bar_time": self.current_bar_time,
            }
        )
        return state

    async def get_orders(self, account_id: str) -> List[Dict[str, Any]]:
        return list(self._orders.values())

    async def cancel_order(self, account_id: str, order_id: str) -> Dict[str, Any]:
        st = self._orders.get(order_id)
        if st:
            st["executionReportStatus"] = "EXECUTION_REPORT_STATUS_CANCELLED"
        return st or {}

    async def connect_websocket(self, user_id: int) -> bool:
        return True

    async def subscribe_prices(self, user_id: int, figis: List[str], queue, candle_interval: Optional[str] = None) -> Dict[str, str]:
        return {f: f for f in figis}

    async def unsubscribe_prices(self, user_id: int, figis: List[str], queue) -> None:
        return None

    async def get_last_price(self, user_id: int, figi: str) -> Optional[float]:
        px = self._mark_price(str(figi or "").upper())
        return px if px > 0 else None

    async def close_websocket(self, user_id: int, queue=None) -> None:
        return None

    async def close(self) -> None:
        return None


__all__ = ["SimBacktestBrokerFacade", "_close_price", "_candle_time_iso"]
