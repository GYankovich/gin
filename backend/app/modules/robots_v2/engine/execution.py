"""Execution Service — single path for paper fills and live broker orders."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.modules.robots.trading.broker_position_sync import money_to_float
from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.contracts import OrderIntent
from app.modules.robots_v2.engine.event_bus import event_bus
from app.modules.robots_v2.engine.paper_ledger import PaperLedger

logger = logging.getLogger(__name__)

_FILL_STATUSES = frozenset({
    "EXECUTION_REPORT_STATUS_FILL",
    "FILL",
    "FILLED",
})
_REJECT_STATUSES = frozenset({
    "EXECUTION_REPORT_STATUS_REJECTED",
    "EXECUTION_REPORT_STATUS_CANCELLED",
    "REJECTED",
    "CANCELLED",
    "CANCELED",
})


@dataclass
class ExecutionResult:
    intent_id: str
    ticker: str
    side: str
    quantity: int
    price: float
    status: str  # filled | rejected | submitted
    mode: str
    pnl: float = 0.0
    broker_order_id: str | None = None
    reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class SymbolGuard:
    """At most one in-flight live order per ticker per robot."""

    def __init__(self) -> None:
        self._inflight: set[str] = set()

    def try_acquire(self, ticker: str) -> bool:
        t = ticker.upper()
        if t in self._inflight:
            return False
        self._inflight.add(t)
        return True

    def release(self, ticker: str) -> None:
        self._inflight.discard(ticker.upper())


class ExecutionService:
    def __init__(
        self,
        *,
        mode: str,
        robot_id: int,
        ledger: PaperLedger,
        slippage_pct: float = 0.5,
        broker: BrokerFacade | None = None,
        account_id: str | None = None,
        instrument_map: dict[str, str] | None = None,
        fill_poll_interval_sec: float = 0.4,
        fill_timeout_sec: float = 15.0,
    ) -> None:
        self.mode = mode
        self.robot_id = robot_id
        self.ledger = ledger
        self.slippage_pct = float(slippage_pct or 0)
        self.broker = broker
        self.account_id = account_id
        self.instrument_map = {k.upper(): v for k, v in (instrument_map or {}).items()}
        self.guard = SymbolGuard()
        self.fill_poll_interval_sec = max(0.1, float(fill_poll_interval_sec))
        self.fill_timeout_sec = max(1.0, float(fill_timeout_sec))

    def _instrument_id(self, ticker: str) -> str:
        t = ticker.upper()
        return self.instrument_map.get(t, t)

    def _apply_slippage(self, side: str, price: float) -> float:
        if price <= 0 or self.slippage_pct <= 0:
            return price
        slip = self.slippage_pct / 100.0
        if side.upper() == "BUY":
            return price * (1.0 + slip)
        return price * (1.0 - slip)

    async def _await_fill(
        self,
        order_id: str,
        *,
        fallback_price: float,
        fallback_qty: int,
    ) -> tuple[str, float, int, dict[str, Any]]:
        """Poll get_order_state until terminal or timeout.

        Returns (status, price, qty, raw_state) where status is filled|rejected|submitted.
        """
        assert self.broker is not None and self.account_id
        deadline = asyncio.get_running_loop().time() + self.fill_timeout_sec
        last: dict[str, Any] = {}
        while asyncio.get_running_loop().time() < deadline:
            try:
                state = await self.broker.get_order_state(self.account_id, order_id)
            except Exception:
                logger.exception("get_order_state failed robot=%s order=%s", self.robot_id, order_id)
                await asyncio.sleep(self.fill_poll_interval_sec)
                continue
            if not isinstance(state, dict):
                await asyncio.sleep(self.fill_poll_interval_sec)
                continue
            last = state
            status_raw = str(
                state.get("executionReportStatus") or state.get("status") or ""
            ).upper()
            lots_exec = money_to_float(state.get("lotsExecuted") or state.get("lots_executed"))
            price = money_to_float(
                state.get("executedOrderPrice")
                or state.get("executed_price")
                or state.get("averagePositionPrice")
            )
            if status_raw in _FILL_STATUSES or (
                "FILL" in status_raw and "PARTIAL" not in status_raw and lots_exec > 0
            ):
                qty = int(lots_exec) if lots_exec > 0 else fallback_qty
                px = price if price > 0 else fallback_price
                return "filled", px, qty, state
            if status_raw in _REJECT_STATUSES or status_raw.endswith("_REJECTED") or status_raw.endswith("_CANCELLED"):
                return "rejected", fallback_price, fallback_qty, state
            # Partial: keep waiting until full fill or timeout
            await asyncio.sleep(self.fill_poll_interval_sec)
        return "submitted", fallback_price, fallback_qty, last

    async def execute_intent(
        self,
        intent: OrderIntent,
        *,
        last_price: float,
        bid: float | None = None,
        ask: float | None = None,
    ) -> ExecutionResult:
        ticker = str(intent.figi or "").upper()
        side = str(intent.side or "BUY").upper()
        qty = int(intent.quantity or 0)
        intent_id = str(getattr(intent, "intent_id", None) or uuid4())
        reduce_only = bool(getattr(intent, "reduce_only", False))

        if qty <= 0 or not ticker:
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=0,
                status="rejected", mode=self.mode, reason="INVALID_QTY_OR_TICKER",
            )

        mid = last_price
        if mid <= 0:
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=0,
                status="rejected", mode=self.mode, reason="STALE_OR_MISSING_PRICE",
            )

        if self.mode == "live" and bid and ask and mid > 0:
            spread_pct = (ask - bid) / mid * 100.0
            if spread_pct > self.slippage_pct:
                await event_bus.publish(self.robot_id, "decision", {
                    "code": "SLIPPAGE_LIMIT_FALLBACK",
                    "ticker": ticker,
                    "spreadPct": spread_pct,
                })

        fill_price = float(intent.price or mid)
        if self.mode == "paper":
            fill_price = self._apply_slippage(side, fill_price)
            pnl = self.ledger.apply_fill(
                ticker=ticker, side=side, quantity=qty, price=fill_price, reduce_only=reduce_only,
            )
            result = ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty,
                price=fill_price, status="filled", mode="paper", pnl=pnl,
                reason=intent.reason,
            )
            await event_bus.publish(self.robot_id, "order", {
                "ticker": ticker, "side": side, "qty": qty, "price": fill_price,
                "status": "filled", "mode": "paper", "kind": intent.kind,
            })
            return result

        # Live
        if self.broker is None or not self.account_id:
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=fill_price,
                status="rejected", mode="live", reason="BROKER_OR_ACCOUNT_MISSING",
            )
        if not self.guard.try_acquire(ticker):
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=fill_price,
                status="rejected", mode="live", reason="IN_FLIGHT_ORDER",
            )
        try:
            instrument = self._instrument_id(ticker)
            direction = "ORDER_DIRECTION_BUY" if side == "BUY" else "ORDER_DIRECTION_SELL"
            broker_type = getattr(self.broker, "broker_type", "")
            if broker_type == "bybit":
                direction = side
            resp = await self.broker.post_market_order(
                instrument, qty, direction, self.account_id,
            )
            order_id = str(
                (resp or {}).get("order_id")
                or (resp or {}).get("orderId")
                or (resp or {}).get("orderLinkId")
                or ""
            ) or None
            await event_bus.publish(self.robot_id, "order", {
                "ticker": ticker, "side": side, "qty": qty, "price": fill_price,
                "status": "submitted", "mode": "live", "orderId": order_id, "kind": intent.kind,
            })

            if not order_id:
                # No id to poll — keep optimistic shadow fill so risk stays consistent; reconcile will fix.
                pnl = self.ledger.apply_fill(
                    ticker=ticker, side=side, quantity=qty, price=fill_price, reduce_only=reduce_only,
                )
                return ExecutionResult(
                    intent_id=intent_id, ticker=ticker, side=side, quantity=qty,
                    price=fill_price, status="submitted", mode="live", pnl=pnl,
                    reason=intent.reason or "NO_ORDER_ID", meta={"raw": resp or {}},
                )

            conf_status, conf_price, conf_qty, state = await self._await_fill(
                order_id, fallback_price=fill_price, fallback_qty=qty,
            )
            if conf_status == "filled":
                pnl = self.ledger.apply_fill(
                    ticker=ticker, side=side, quantity=conf_qty, price=conf_price, reduce_only=reduce_only,
                )
                result = ExecutionResult(
                    intent_id=intent_id, ticker=ticker, side=side, quantity=conf_qty,
                    price=conf_price, status="filled", mode="live", pnl=pnl,
                    broker_order_id=order_id, reason=intent.reason, meta={"raw": state},
                )
                await event_bus.publish(self.robot_id, "order", {
                    "ticker": ticker, "side": side, "qty": conf_qty, "price": conf_price,
                    "status": "filled", "mode": "live", "orderId": order_id, "kind": intent.kind,
                })
                return result

            if conf_status == "rejected":
                result = ExecutionResult(
                    intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=fill_price,
                    status="rejected", mode="live", broker_order_id=order_id,
                    reason="BROKER_REJECTED_OR_CANCELLED", meta={"raw": state},
                )
                await event_bus.publish(self.robot_id, "order", {
                    "ticker": ticker, "side": side, "qty": qty, "price": fill_price,
                    "status": "rejected", "mode": "live", "orderId": order_id, "kind": intent.kind,
                })
                return result

            # Timeout — leave ledger untouched; ADR-11 reconcile will pick up broker state.
            await event_bus.publish(self.robot_id, "health", {
                "level": "warn",
                "message": "fill confirmation timeout",
                "ticker": ticker,
                "orderId": order_id,
            })
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=fill_price,
                status="submitted", mode="live", broker_order_id=order_id,
                reason="FILL_CONFIRM_TIMEOUT", meta={"raw": state},
            )
        except Exception as exc:
            logger.exception("live order failed robot=%s ticker=%s", self.robot_id, ticker)
            await event_bus.publish(self.robot_id, "health", {
                "level": "error", "message": f"order failed: {exc}", "ticker": ticker,
            })
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=fill_price,
                status="rejected", mode="live", reason=str(exc)[:500],
            )
        finally:
            self.guard.release(ticker)
