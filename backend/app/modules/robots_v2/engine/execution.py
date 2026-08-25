"""Execution Service — single path for paper fills and live broker orders."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.modules.robots.trading.broker_position_sync import money_to_float
from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots.trading.contracts import OrderIntent
from app.modules.robots_v2.engine.broker_factory import _looks_like_figi
from app.modules.robots_v2.engine.event_bus import event_bus
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.engine.session_log import log_external_api
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
_SKIP_TICKER_ISSUE_REASONS = frozenset({
    "REJECT_COOLDOWN",
    "BROKER_OR_ACCOUNT_MISSING",
    "IN_FLIGHT_ORDER",
})
_FIGI_WARN = "FIGI не сопоставлен — заявки по тикеру брокер отклонит"
_TICKER_ISSUE_LABELS = {
    "FIGI_UNRESOLVED": "Нет FIGI у брокера — ордер не отправлен",
    "STALE_OR_MISSING_PRICE": "Нет актуальной цены для заявки",
    "INVALID_QTY_OR_TICKER": "Некорректный тикер или количество",
    "FILL_CONFIRM_TIMEOUT": "Нет подтверждения исполнения заявки",
    "BROKER_REJECTED": "Брокер отклонил заявку",
}


@dataclass
class RestingOrder:
    """Open LIMIT order tracked locally until fill or cancel."""

    intent_id: str
    ticker: str
    side: str
    quantity: int
    limit_price: float
    reduce_only: bool = False
    reason: str | None = None
    kind: str | None = None
    broker_order_id: str | None = None


@dataclass
class ExecutionResult:
    intent_id: str
    ticker: str
    side: str
    quantity: int
    price: float
    status: str  # filled | rejected | submitted | resting
    mode: str
    pnl: float = 0.0
    broker_order_id: str | None = None
    reason: str | None = None
    kind: str | None = None
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
        limit_fill_timeout_sec: float = 2.0,
        user_id: int | None = None,
        token_id: int | None = None,
        action_log: Any | None = None,
        quiet: bool = False,
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
        self.limit_fill_timeout_sec = max(0.5, float(limit_fill_timeout_sec))
        self.user_id = user_id
        self.token_id = token_id
        self.action_log = action_log
        self.quiet = bool(quiet)
        self._resting: dict[str, RestingOrder] = {}
        # After a broker reject, skip re-submits for a short window (avoids spam).
        self._reject_cooldown_until: dict[str, float] = {}
        self.reject_cooldown_sec = 45.0
        self._last_order_sync_at: float = 0.0
        self.order_sync_min_interval_sec = 5.0
        self._known_broker_order_ids: set[str] = set()
        self._resting_submitted_at: dict[str, float] = {}
        self._resting_grace_sec = 45.0
        self._ticker_issues: dict[str, str] = {}

    @staticmethod
    def _humanize_ticker_issue(reason: str) -> str:
        raw = str(reason or "").strip()
        if not raw:
            return ""
        mapped = _TICKER_ISSUE_LABELS.get(raw)
        if mapped:
            return mapped
        low = raw.lower()
        if "50002" in raw or "instrument not found" in low:
            return "Брокер не нашёл инструмент (FIGI/тикер)"
        if "figi" in low and "unresolved" in low:
            return _TICKER_ISSUE_LABELS["FIGI_UNRESOLVED"]
        return raw[:280]

    def note_ticker_issue(self, ticker: str, message: str) -> None:
        t = str(ticker or "").upper()
        msg = self._humanize_ticker_issue(message)
        if t and msg:
            self._ticker_issues[t] = msg

    def clear_ticker_issue(self, ticker: str) -> None:
        self._ticker_issues.pop(str(ticker or "").upper(), None)

    def ticker_warning(self, ticker: str, *, last_price: float | None = None) -> str | None:
        t = str(ticker or "").upper()
        if not t:
            return None
        parts: list[str] = []
        stored = self._ticker_issues.get(t)
        if stored:
            parts.append(stored)
        elif self.mode == "live" and getattr(self.broker, "broker_type", "") == "tinvest":
            instrument = str(self.instrument_map.get(t) or t)
            if not self._tinvest_instrument_ready(instrument):
                parts.append(_FIGI_WARN)
        if last_price is not None and float(last_price) <= 0:
            parts.append("Нет актуальной котировки")
        return " · ".join(parts) if parts else None

    def _track_execution_result(self, result: ExecutionResult) -> ExecutionResult:
        ticker = str(result.ticker or "")
        reason = str(result.reason or "").strip()
        if result.status in ("filled", "resting"):
            self.clear_ticker_issue(ticker)
        elif result.status == "rejected" and reason and reason not in _SKIP_TICKER_ISSUE_REASONS:
            self.note_ticker_issue(ticker, reason)
        elif result.status == "submitted" and reason == "FILL_CONFIRM_TIMEOUT":
            self.note_ticker_issue(ticker, reason)
        return result

    def _log(self, message: str) -> None:
        if self.quiet:
            return
        if self.action_log is not None:
            self.action_log.info(message)
        else:
            logger.info("[robot=%s] %s", self.robot_id, message)

    @staticmethod
    def _mono() -> float:
        try:
            return asyncio.get_running_loop().time()
        except RuntimeError:
            return time.monotonic()

    def _mark_reject_cooldown(self, ticker: str) -> None:
        t = ticker.upper()
        if not t:
            return
        self._reject_cooldown_until[t] = self._mono() + float(self.reject_cooldown_sec)

    def _on_reject_cooldown(self, ticker: str) -> bool:
        t = ticker.upper()
        until = self._reject_cooldown_until.get(t)
        if until is None:
            return False
        now = self._mono()
        if now >= until:
            self._reject_cooldown_until.pop(t, None)
            return False
        return True

    @staticmethod
    def _broker_reject_message(exc: BaseException | None = None, state: dict[str, Any] | None = None) -> str:
        """Prefer human-readable broker/API text over opaque status codes."""
        if isinstance(state, dict):
            for key in (
                "message",
                "Message",
                "rejectReasonDescription",
                "reject_reason_description",
                "statusMessage",
                "errorMessage",
                "error_message",
            ):
                val = state.get(key)
                if val is not None and str(val).strip():
                    return str(val).strip()[:500]
            status_raw = str(
                state.get("executionReportStatus") or state.get("status") or ""
            ).strip()
            if status_raw:
                return f"Заявка отклонена/отменена брокером ({status_raw})"
        if exc is not None:
            text = str(exc).strip()
            if text:
                return text[:500]
        return "BROKER_REJECTED"

    def update_instrument_map(self, mapping: dict[str, str] | None) -> None:
        """Merge ticker→broker-id after universe refresh. Prefer FIGI over ticker placeholder."""
        for key, raw in (mapping or {}).items():
            ticker = str(key or "").upper()
            instrument = str(raw or "").strip().upper()
            if not ticker or not instrument:
                continue
            prev = str(self.instrument_map.get(ticker) or "").upper()
            if not prev or prev == ticker or instrument != ticker:
                self.instrument_map[ticker] = instrument
            resolved = str(self.instrument_map.get(ticker) or "")
            if self._tinvest_instrument_ready(resolved):
                prev_issue = self._ticker_issues.get(ticker) or ""
                if prev_issue and (
                    "FIGI" in prev_issue
                    or "не сопоставлен" in prev_issue
                    or "не нашёл инструмент" in prev_issue
                ):
                    self.clear_ticker_issue(ticker)

    def _instrument_id(self, ticker: str) -> str:
        t = ticker.upper()
        return self.instrument_map.get(t, t)

    def _tinvest_instrument_ready(self, instrument: str) -> bool:
        broker_type = getattr(self.broker, "broker_type", "")
        if broker_type != "tinvest":
            return True
        return _looks_like_figi(instrument)

    @staticmethod
    def _fill_unit_price(raw_price: float, qty: int, *, ref_px: float | None) -> float:
        from app.modules.robots_v2.audit_pnl import normalize_live_fill_price

        px = float(raw_price or 0)
        q = int(qty or 0)
        if q > 1 and px > 0:
            return normalize_live_fill_price(px, q, ref_px=ref_px)
        if px > 0:
            return px
        return float(ref_px or 0)

    def _apply_slippage(self, side: str, price: float) -> float:
        if price <= 0 or self.slippage_pct <= 0:
            return price
        slip = self.slippage_pct / 100.0
        if side.upper() == "BUY":
            return price * (1.0 + slip)
        return price * (1.0 - slip)

    @staticmethod
    def _limit_would_fill(side: str, mark: float, limit: float) -> bool:
        if limit <= 0 or mark <= 0:
            return False
        s = side.upper()
        if s == "SELL":
            return mark >= limit
        return mark <= limit

    @staticmethod
    def _same_resting(ro: RestingOrder, *, side: str, qty: int, limit_price: float) -> bool:
        return (
            ro.side == side.upper()
            and ro.quantity == qty
            and abs(ro.limit_price - limit_price) < 1e-6
        )

    @staticmethod
    def _is_active_broker_status(status_raw: str) -> bool:
        from app.modules.robots_v2.engine.order_sync import classify_order_lifecycle

        s = str(status_raw or "").upper()
        if classify_order_lifecycle(s) == "active":
            return True
        return s in (
            "EXECUTION_REPORT_STATUS_NEW",
            "EXECUTION_REPORT_STATUS_PARTIALLYFILL",
            "EXECUTION_REPORT_STATUS_PARTIAL_FILL",
            "PENDING_NEW",
            "PENDINGNEW",
        )

    async def _adopt_open_broker_limit(self, ticker: str, *, side: str) -> RestingOrder | None:
        """If broker already has an active LIMIT on ticker, adopt it instead of re-posting."""
        if self.mode != "live" or self.broker is None or not self.account_id:
            return None
        t = ticker.upper()
        existing = self._resting.get(t)
        if existing is not None and existing.broker_order_id:
            return existing

        get_orders = getattr(self.broker, "get_orders", None)
        if not callable(get_orders):
            return None
        try:
            raw = await get_orders(self.account_id)
        except Exception as exc:
            self._log(f"ADOPT get_orders failed {t}: {exc}")
            return None

        from app.modules.robots_v2.engine.order_sync import (
            filter_robot_scope_orders,
            normalize_broker_orders,
            pick_resting_per_ticker,
        )

        position_tickers = {str(k).upper() for k in self.ledger.positions.keys()}
        known = set(self._known_broker_order_ids)
        for ro in self._resting.values():
            if ro.broker_order_id:
                known.add(str(ro.broker_order_id))

        normalized = normalize_broker_orders(
            raw if isinstance(raw, list) else [],
            instrument_map=self.instrument_map,
        )
        scoped = filter_robot_scope_orders(
            normalized,
            position_tickers=position_tickers,
            known_order_ids=known,
        )
        active = [
            o for o in scoped
            if o.lifecycle == "active" and o.order_type != "MARKET" and o.ticker.upper() == t
        ]
        if side.upper() == "SELL":
            active = [o for o in active if o.side == "SELL"] or active
        chosen = pick_resting_per_ticker(active, prefer_order_ids=known)
        bo = chosen.get(t)
        if bo is None:
            return None

        ro = RestingOrder(
            intent_id=str(uuid4()),
            ticker=t,
            side=bo.side,
            quantity=bo.quantity if bo.quantity > 0 else 1,
            limit_price=float(bo.limit_price or 0),
            reduce_only=True,
            reason="take_profit",
            kind="exit_sl_tp",
            broker_order_id=bo.order_id,
        )
        self._resting[t] = ro
        self.remember_broker_order_id(bo.order_id)
        self._log(f"ADOPT broker LIMIT {t} orderId={bo.order_id} @ {bo.limit_price:.6g}")
        return ro

    async def _cancel_duplicate_broker_limits(
        self,
        active_orders: list[Any],
        *,
        prefer_order_ids: set[str],
    ) -> list[ExecutionResult]:
        """Cancel extra active LIMIT orders on the same ticker (keep one)."""
        if self.mode != "live" or self.broker is None or not self.account_id:
            return []

        from app.modules.robots_v2.engine.order_sync import pick_resting_per_ticker

        by_ticker: dict[str, list[Any]] = {}
        for o in active_orders:
            if getattr(o, "lifecycle", "") != "active" or getattr(o, "order_type", "") == "MARKET":
                continue
            by_ticker.setdefault(str(o.ticker).upper(), []).append(o)

        results: list[ExecutionResult] = []
        for ticker, group in by_ticker.items():
            if len(group) <= 1:
                continue
            keep = pick_resting_per_ticker(group, prefer_order_ids=prefer_order_ids).get(ticker)
            if keep is None:
                continue
            for o in group:
                if o.order_id == keep.order_id:
                    continue
                try:
                    await self.broker.cancel_order(self.account_id, o.order_id)
                    self._log(f"ORDER_SYNC cancel duplicate {ticker} orderId={o.order_id}")
                    results.append(
                        ExecutionResult(
                            intent_id=str(uuid4()),
                            ticker=ticker,
                            side=str(o.side),
                            quantity=int(o.quantity or 0),
                            price=float(o.limit_price or 0),
                            status="cancelled",
                            mode="live",
                            broker_order_id=o.order_id,
                            reason="DUPLICATE_TP",
                            kind="exit_sl_tp",
                            meta={"source": "order_sync", "orderType": "LIMIT"},
                        )
                    )
                except Exception as exc:
                    self._log(f"ORDER_SYNC cancel duplicate failed {ticker} {o.order_id}: {exc}")
        return results

    def remember_broker_order_id(self, order_id: str | None) -> None:
        oid = str(order_id or "").strip()
        if oid:
            self._known_broker_order_ids.add(oid)

    async def sync_orders_from_broker(
        self,
        *,
        force: bool = False,
        known_order_ids: set[str] | None = None,
    ) -> list[ExecutionResult]:
        """Rebuild resting from GetOrders; resolve missing locals via get_order_state.

        Returns fill/cancel results for the cycle audit path.
        Paper mode: no-op (local resting + poll_resting_fills remain authoritative).
        """
        if self.mode != "live" or self.broker is None or not self.account_id:
            return []

        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:
            now = 0.0
        if (
            not force
            and self._last_order_sync_at > 0
            and (now - self._last_order_sync_at) < float(self.order_sync_min_interval_sec)
        ):
            return []
        self._last_order_sync_at = now

        from app.modules.robots_v2.engine.order_sync import (
            filter_robot_scope_orders,
            normalize_broker_orders,
            pick_resting_per_ticker,
        )

        get_orders = getattr(self.broker, "get_orders", None)
        if not callable(get_orders):
            return []

        started = datetime.now(timezone.utc)
        broker_type = getattr(self.broker, "broker_type", "") or "broker"
        try:
            raw = await get_orders(self.account_id)
            if broker_type != "bybit":
                await log_external_api(
                    robot_id=self.robot_id,
                    user_id=self.user_id,
                    token_id=self.token_id,
                    endpoint=f"{broker_type}.get_orders",
                    request_data={"account_id": self.account_id},
                    response_data={"count": len(raw) if isinstance(raw, list) else None},
                    response_status=200,
                    started_at=started,
                )
        except Exception as exc:
            logger.exception("sync_orders get_orders failed robot=%s", self.robot_id)
            self._log(f"ORDER_SYNC get_orders failed: {exc}")
            if broker_type != "bybit":
                await log_external_api(
                    robot_id=self.robot_id,
                    user_id=self.user_id,
                    token_id=self.token_id,
                    endpoint=f"{broker_type}.get_orders",
                    request_data={"account_id": self.account_id},
                    error_message=str(exc)[:500],
                    started_at=started,
                )
            return []

        if not isinstance(raw, list):
            raw = []

        known = set(self._known_broker_order_ids)
        if known_order_ids:
            known |= {str(x).strip() for x in known_order_ids if x}
        for ro in self._resting.values():
            if ro.broker_order_id:
                known.add(str(ro.broker_order_id))

        position_tickers = {str(t).upper() for t in self.ledger.positions.keys()}
        normalized = normalize_broker_orders(raw, instrument_map=self.instrument_map)
        scoped = filter_robot_scope_orders(
            normalized,
            position_tickers=position_tickers,
            known_order_ids=known,
        )
        open_ids = {o.order_id for o in scoped if o.lifecycle == "active"}
        for oid in open_ids:
            self.remember_broker_order_id(oid)

        results: list[ExecutionResult] = []
        # Local resting missing from GetOrders → resolve terminal state.
        for ticker, ro in list(self._resting.items()):
            oid = str(ro.broker_order_id or "").strip()
            if oid and oid in open_ids:
                continue
            if not oid:
                # Adopted-less local paper-like entry shouldn't happen in live.
                self._resting.pop(ticker, None)
                continue
            try:
                state = await self.broker.get_order_state(self.account_id, oid)
            except Exception as exc:
                logger.exception(
                    "sync_orders get_order_state failed robot=%s order=%s",
                    self.robot_id,
                    oid,
                )
                self._log(f"ORDER_SYNC state failed {ticker} {oid}: {exc}")
                continue
            if not isinstance(state, dict):
                self._resting.pop(ticker, None)
                continue
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
                qty = int(lots_exec) if lots_exec > 0 else ro.quantity
                px = self._fill_unit_price(price, qty, ref_px=float(ro.limit_price or 0) or None)
                self._resting.pop(ticker, None)
                results.append(
                    await self._fill_resting(
                        ro,
                        fill_price=px,
                        fill_qty=qty,
                        meta={"raw": state, "source": "order_sync", "orderType": "LIMIT"},
                    )
                )
            elif (
                status_raw in _REJECT_STATUSES
                or status_raw.endswith("_REJECTED")
                or status_raw.endswith("_CANCELLED")
                or status_raw.endswith("_CANCELED")
            ):
                self._resting.pop(ticker, None)
                reject_msg = self._broker_reject_message(state=state)
                terminal = "rejected" if "REJECT" in status_raw else "cancelled"
                self._log(f"ORDER_SYNC {terminal} {ticker} orderId={oid}: {reject_msg}")
                results.append(
                    ExecutionResult(
                        intent_id=ro.intent_id,
                        ticker=ro.ticker,
                        side=ro.side,
                        quantity=ro.quantity,
                        price=ro.limit_price,
                        status=terminal,
                        mode="live",
                        broker_order_id=oid,
                        reason=reject_msg,
                        kind=ro.kind or "exit_sl_tp",
                        meta={"raw": state, "source": "order_sync", "orderType": "LIMIT"},
                    )
                )
            else:
                if self._is_active_broker_status(status_raw):
                    self._log(
                        f"ORDER_SYNC keep {ticker} orderId={oid} status={status_raw or 'active'}"
                    )
                    continue
                # Unknown terminal/absent — drop local track.
                self._resting.pop(ticker, None)
                self._log(
                    f"ORDER_SYNC drop {ticker} orderId={oid} status={status_raw or 'missing'}"
                )

        prefer_ids = {
            str(ro.broker_order_id)
            for ro in self._resting.values()
            if ro.broker_order_id
        } | known
        active_scoped = [o for o in scoped if o.lifecycle == "active"]
        dup_results = await self._cancel_duplicate_broker_limits(
            active_scoped,
            prefer_order_ids=prefer_ids,
        )
        results.extend(dup_results)
        open_ids = {o.order_id for o in active_scoped if o.lifecycle == "active"}
        for dr in dup_results:
            if dr.broker_order_id:
                open_ids.discard(str(dr.broker_order_id))

        chosen = pick_resting_per_ticker(
            [o for o in active_scoped if o.order_id in open_ids or o.lifecycle == "active"],
            prefer_order_ids=prefer_ids,
        )

        prev = dict(self._resting)
        new_resting: dict[str, RestingOrder] = {}
        for ticker, bo in chosen.items():
            old = prev.get(ticker)
            same = old is not None and str(old.broker_order_id or "") == bo.order_id
            new_resting[ticker] = RestingOrder(
                intent_id=old.intent_id if same and old else str(uuid4()),
                ticker=ticker,
                side=bo.side,
                quantity=bo.quantity if bo.quantity > 0 else (old.quantity if old else 0),
                limit_price=float(bo.limit_price or (old.limit_price if old else 0) or 0),
                reduce_only=bool(bo.reduce_only or (old.reduce_only if old else True)),
                reason=(old.reason if same and old else "broker_sync"),
                kind=(old.kind if same and old else "exit_sl_tp"),
                broker_order_id=bo.order_id,
            )
            self.remember_broker_order_id(bo.order_id)

        try:
            loop_now = asyncio.get_running_loop().time()
        except RuntimeError:
            loop_now = 0.0
        for ticker, ro in prev.items():
            if ticker in new_resting:
                continue
            if not ro.broker_order_id:
                continue
            if str(ro.broker_order_id) in open_ids:
                new_resting[ticker] = ro
                continue
            submitted_at = self._resting_submitted_at.get(ticker.upper(), 0.0)
            if submitted_at and loop_now and (loop_now - submitted_at) < self._resting_grace_sec:
                new_resting[ticker] = ro

        adopted = sorted(set(new_resting) - set(prev))
        dropped = sorted(set(prev) - set(new_resting))
        self._resting = new_resting
        self._log(
            f"ORDER_SYNC open={len(new_resting)} fills={sum(1 for r in results if r.status == 'filled')} "
            f"adopted={adopted} dropped={dropped}"
        )
        return results

    def _resting_result(self, ro: RestingOrder, *, reason: str | None = None) -> ExecutionResult:
        return ExecutionResult(
            intent_id=ro.intent_id,
            ticker=ro.ticker,
            side=ro.side,
            quantity=ro.quantity,
            price=ro.limit_price,
            status="resting",
            mode=self.mode,
            broker_order_id=ro.broker_order_id,
            reason=reason or ro.reason,
            kind=ro.kind,
        )

    def cancel_resting_local(self, ticker: str) -> None:
        t = ticker.upper()
        if self._resting.pop(t, None) is not None:
            self._log(f"CANCEL RESTING (local) {t}")

    def poll_resting_fills_sync(
        self,
        *,
        last_prices: dict[str, float] | None = None,
    ) -> list[ExecutionResult]:
        """Paper mark-cross fills without event-loop hops."""
        if not self._resting:
            return []
        prices = {k.upper(): float(v) for k, v in (last_prices or {}).items() if v}
        results: list[ExecutionResult] = []
        for ticker in list(self._resting.keys()):
            ro = self._resting.get(ticker)
            if ro is None:
                continue
            mark = prices.get(ticker, 0.0)
            if not self._limit_would_fill(ro.side, mark, ro.limit_price):
                continue
            self._resting.pop(ticker, None)
            results.append(self._fill_resting_sync(ro, fill_price=ro.limit_price))
        return results

    def _fill_resting_sync(
        self,
        ro: RestingOrder,
        *,
        fill_price: float,
        fill_qty: int | None = None,
        broker_order_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        qty = fill_qty if fill_qty is not None else ro.quantity
        px = fill_price if fill_price > 0 else ro.limit_price
        pnl = self.ledger.apply_fill(
            ticker=ro.ticker,
            side=ro.side,
            quantity=qty,
            price=px,
            reduce_only=ro.reduce_only,
        )
        oid = broker_order_id or ro.broker_order_id
        self._log(
            f"{self.mode.upper()} LIMIT FILL {ro.side} {ro.ticker} qty={qty} "
            f"price={px:.6g} kind={ro.kind} pnl={pnl:.4f}"
        )
        return ExecutionResult(
            intent_id=ro.intent_id,
            ticker=ro.ticker,
            side=ro.side,
            quantity=qty,
            price=px,
            status="filled",
            mode=self.mode,
            pnl=pnl,
            broker_order_id=oid,
            reason=ro.reason,
            kind=ro.kind,
            meta=meta or {},
        )

    def execute_intent_sync(
        self,
        intent: OrderIntent,
        *,
        last_price: float,
    ) -> ExecutionResult:
        """Paper MARKET/LIMIT path with no awaits (backtest hot loop)."""
        ticker = str(intent.figi or "").upper()
        side = str(intent.side or "BUY").upper()
        qty = int(intent.quantity or 0)
        intent_id = str(getattr(intent, "intent_id", None) or uuid4())
        reduce_only = bool(getattr(intent, "reduce_only", False))
        intent_kind = str(getattr(intent, "kind", None) or "entry")
        order_type = str(getattr(intent, "order_type", None) or "MARKET").upper()

        if qty <= 0 or not ticker:
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=0,
                status="rejected", mode=self.mode, reason="INVALID_QTY_OR_TICKER", kind=intent_kind,
            )
        mid = last_price
        if mid <= 0:
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=0,
                status="rejected", mode=self.mode, reason="STALE_OR_MISSING_PRICE", kind=intent_kind,
            )
        if self._on_reject_cooldown(ticker):
            return ExecutionResult(
                intent_id=intent_id,
                ticker=ticker,
                side=side,
                quantity=qty,
                price=float(intent.price or mid),
                status="rejected",
                mode=self.mode,
                reason="REJECT_COOLDOWN",
                kind=intent_kind,
            )

        if order_type == "LIMIT":
            limit_price = float(intent.price or mid)
            existing = self._resting.get(ticker)
            if existing is not None and self._same_resting(
                existing, side=side, qty=qty, limit_price=limit_price,
            ):
                return self._resting_result(existing, reason="ALREADY_RESTING")
            if existing is not None:
                self.cancel_resting_local(ticker)
            if self._limit_would_fill(side, mid, limit_price):
                pnl = self.ledger.apply_fill(
                    ticker=ticker, side=side, quantity=qty, price=limit_price, reduce_only=reduce_only,
                )
                result = ExecutionResult(
                    intent_id=intent_id, ticker=ticker, side=side, quantity=qty,
                    price=limit_price, status="filled", mode="paper", pnl=pnl,
                    reason=intent.reason, kind=intent_kind,
                )
                self._log(
                    f"PAPER LIMIT FILL {side} {ticker} qty={qty} price={limit_price:.6g} "
                    f"kind={intent.kind} pnl={pnl:.4f}"
                )
                return result
            ro = RestingOrder(
                intent_id=intent_id,
                ticker=ticker,
                side=side,
                quantity=qty,
                limit_price=limit_price,
                reduce_only=reduce_only,
                reason=intent.reason,
                kind=intent_kind,
            )
            self._resting[ticker] = ro
            self._log(f"PAPER LIMIT RESTING {side} {ticker} qty={qty} @ {limit_price:.6g}")
            return self._resting_result(ro)

        if str(intent.reason or "") == "stop_loss":
            self.cancel_resting_local(ticker)
        fill_price = self._apply_slippage(side, float(intent.price or mid))
        pnl = self.ledger.apply_fill(
            ticker=ticker, side=side, quantity=qty, price=fill_price, reduce_only=reduce_only,
        )
        result = ExecutionResult(
            intent_id=intent_id, ticker=ticker, side=side, quantity=qty,
            price=fill_price, status="filled", mode="paper", pnl=pnl,
            reason=intent.reason, kind=intent_kind,
        )
        self._log(
            f"PAPER FILL {side} {ticker} qty={qty} price={fill_price:.6g} kind={intent.kind} pnl={pnl:.4f}"
        )
        return result

    async def cancel_resting(self, ticker: str) -> None:
        """Cancel broker resting LIMIT (if live) and drop local tracking."""
        t = ticker.upper()
        ro = self._resting.pop(t, None)
        if ro is None:
            return
        if self.mode != "live" or not self.broker or not self.account_id or not ro.broker_order_id:
            self._log(f"CANCEL RESTING (local) {t}")
            return
        try:
            await self.broker.cancel_order(self.account_id, ro.broker_order_id)
            self._log(f"CANCEL RESTING {t} orderId={ro.broker_order_id}")
        except Exception as exc:
            logger.exception("cancel_resting failed robot=%s ticker=%s", self.robot_id, t)
            self._log(f"CANCEL RESTING ERROR {t}: {exc}")

    async def _fill_resting(
        self,
        ro: RestingOrder,
        *,
        fill_price: float,
        fill_qty: int | None = None,
        broker_order_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        qty = fill_qty if fill_qty is not None else ro.quantity
        px = fill_price if fill_price > 0 else ro.limit_price
        pnl = self.ledger.apply_fill(
            ticker=ro.ticker,
            side=ro.side,
            quantity=qty,
            price=px,
            reduce_only=ro.reduce_only,
        )
        oid = broker_order_id or ro.broker_order_id
        self._log(
            f"{self.mode.upper()} LIMIT FILL {ro.side} {ro.ticker} qty={qty} "
            f"price={px:.6g} kind={ro.kind} pnl={pnl:.4f}"
        )
        if not self.quiet:
            await event_bus.publish(self.robot_id, "order", {
            "ticker": ro.ticker,
            "side": ro.side,
            "qty": qty,
            "price": px,
            "status": "filled",
            "mode": self.mode,
            "orderId": oid,
            "kind": ro.kind,
        })
        return ExecutionResult(
            intent_id=ro.intent_id,
            ticker=ro.ticker,
            side=ro.side,
            quantity=qty,
            price=px,
            status="filled",
            mode=self.mode,
            pnl=pnl,
            broker_order_id=oid,
            reason=ro.reason,
            kind=ro.kind,
            meta=meta or {},
        )

    async def poll_resting_fills(
        self,
        *,
        last_prices: dict[str, float] | None = None,
    ) -> list[ExecutionResult]:
        """Detect resting LIMIT fills via mark cross (paper) or broker poll (live)."""
        if not self._resting:
            return []

        if self.mode == "paper":
            return self.poll_resting_fills_sync(last_prices=last_prices)

        results: list[ExecutionResult] = []
        for ticker in list(self._resting.keys()):
            ro = self._resting.get(ticker)
            if ro is None:
                continue
            if self.broker is None or not self.account_id or not ro.broker_order_id:
                continue
            try:
                state = await self.broker.get_order_state(self.account_id, ro.broker_order_id)
            except Exception:
                logger.exception(
                    "poll_resting get_order_state failed robot=%s ticker=%s",
                    self.robot_id,
                    ticker,
                )
                continue
            if not isinstance(state, dict):
                continue
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
                qty = int(lots_exec) if lots_exec > 0 else ro.quantity
                px = self._fill_unit_price(price, qty, ref_px=float(ro.limit_price or 0) or None)
                self._resting.pop(ticker, None)
                results.append(
                    await self._fill_resting(
                        ro,
                        fill_price=px,
                        fill_qty=qty,
                        meta={"raw": state},
                    )
                )
            elif status_raw in _REJECT_STATUSES or status_raw.endswith("_REJECTED") or status_raw.endswith("_CANCELLED"):
                self._resting.pop(ticker, None)
                self._log(f"RESTING REMOVED {ticker} broker_status={status_raw}")

        return results

    async def _await_fill(
        self,
        order_id: str,
        *,
        fallback_price: float,
        fallback_qty: int,
        timeout_sec: float | None = None,
    ) -> tuple[str, float, int, dict[str, Any]]:
        """Poll get_order_state until terminal or timeout.

        Returns (status, price, qty, raw_state) where status is filled|rejected|submitted.
        """
        assert self.broker is not None and self.account_id
        deadline = asyncio.get_running_loop().time() + (
            self.fill_timeout_sec if timeout_sec is None else max(0.5, float(timeout_sec))
        )
        last: dict[str, Any] = {}
        while asyncio.get_running_loop().time() < deadline:
            try:
                poll_started = datetime.now(timezone.utc)
                state = await self.broker.get_order_state(self.account_id, order_id)
                broker_type = getattr(self.broker, "broker_type", "")
                if broker_type != "bybit":
                    await log_external_api(
                        robot_id=self.robot_id,
                        user_id=self.user_id,
                        token_id=self.token_id,
                        endpoint=f"{broker_type or 'broker'}.get_order_state",
                        request_data={"account_id": self.account_id, "order_id": order_id},
                        response_data={
                            "status": (state or {}).get("executionReportStatus") if isinstance(state, dict) else None,
                            "lotsExecuted": (state or {}).get("lotsExecuted") if isinstance(state, dict) else None,
                        },
                        response_status=200,
                        started_at=poll_started,
                    )
            except Exception as exc:
                logger.exception("get_order_state failed robot=%s order=%s", self.robot_id, order_id)
                broker_type = getattr(self.broker, "broker_type", "")
                if broker_type != "bybit":
                    await log_external_api(
                        robot_id=self.robot_id,
                        user_id=self.user_id,
                        token_id=self.token_id,
                        endpoint=f"{broker_type or 'broker'}.get_order_state",
                        request_data={"account_id": self.account_id, "order_id": order_id},
                        error_message=str(exc)[:500],
                        started_at=datetime.now(timezone.utc),
                    )
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
                ref_px = fallback_price if fallback_price > 0 else None
                px = self._fill_unit_price(price, qty, ref_px=ref_px)
                return "filled", px, qty, state
            if status_raw in _REJECT_STATUSES or status_raw.endswith("_REJECTED") or status_raw.endswith("_CANCELLED"):
                return "rejected", fallback_price, fallback_qty, state
            await asyncio.sleep(self.fill_poll_interval_sec)
        return "submitted", fallback_price, fallback_qty, last

    async def _execute_market_live(
        self,
        intent: OrderIntent,
        *,
        ticker: str,
        side: str,
        qty: int,
        fill_price: float,
        intent_id: str,
        reduce_only: bool,
        intent_kind: str,
    ) -> ExecutionResult:
        assert self.broker is not None and self.account_id
        if str(intent.reason or "") == "stop_loss":
            await self.cancel_resting(ticker)

        if not self.guard.try_acquire(ticker):
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=fill_price,
                status="rejected", mode="live", reason="IN_FLIGHT_ORDER", kind=intent_kind,
            )
        try:
            instrument = self._instrument_id(ticker)
            direction = "ORDER_DIRECTION_BUY" if side == "BUY" else "ORDER_DIRECTION_SELL"
            broker_type = getattr(self.broker, "broker_type", "")
            if broker_type == "bybit":
                direction = side
            if not self._tinvest_instrument_ready(instrument):
                self._log(f"LIVE ORDER SKIP {ticker}: FIGI unresolved (got {instrument})")
                return ExecutionResult(
                    intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=fill_price,
                    status="rejected", mode="live", reason="FIGI_UNRESOLVED", kind=intent_kind,
                )
            endpoint = f"{broker_type or 'broker'}.post_market_order"
            started = datetime.now(timezone.utc)
            self._log(f"LIVE ORDER submit {side} {ticker}→{instrument} qty={qty} dir={direction}")
            try:
                resp = await self.broker.post_market_order(
                    instrument, qty, direction, self.account_id,
                )
                if broker_type != "bybit":
                    await log_external_api(
                        robot_id=self.robot_id,
                        user_id=self.user_id,
                        token_id=self.token_id,
                        endpoint=endpoint,
                        request_data={
                            "instrument": instrument, "qty": qty, "direction": direction,
                            "account_id": self.account_id,
                        },
                        response_data=resp if isinstance(resp, dict) else {"raw": str(resp)},
                        response_status=200,
                        started_at=started,
                    )
            except Exception as exc:
                if broker_type != "bybit":
                    await log_external_api(
                        robot_id=self.robot_id,
                        user_id=self.user_id,
                        token_id=self.token_id,
                        endpoint=endpoint,
                        request_data={
                            "instrument": instrument, "qty": qty, "direction": direction,
                            "account_id": self.account_id,
                        },
                        error_message=str(exc)[:500],
                        started_at=started,
                    )
                raise
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
                pnl = self.ledger.apply_fill(
                    ticker=ticker, side=side, quantity=qty, price=fill_price, reduce_only=reduce_only,
                )
                return ExecutionResult(
                    intent_id=intent_id, ticker=ticker, side=side, quantity=qty,
                    price=fill_price, status="submitted", mode="live", pnl=pnl,
                    reason=intent.reason or "NO_ORDER_ID", meta={"raw": resp or {}}, kind=intent_kind,
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
                    broker_order_id=order_id, reason=intent.reason, meta={"raw": state}, kind=intent_kind,
                )
                self._log(
                    f"LIVE FILL {side} {ticker} qty={conf_qty} price={conf_price:.6g} "
                    f"orderId={order_id} kind={intent.kind} pnl={pnl:.4f}"
                )
                await event_bus.publish(self.robot_id, "order", {
                    "ticker": ticker, "side": side, "qty": conf_qty, "price": conf_price,
                    "status": "filled", "mode": "live", "orderId": order_id, "kind": intent.kind,
                })
                return result

            if conf_status == "rejected":
                reject_msg = self._broker_reject_message(state=state if isinstance(state, dict) else None)
                self._mark_reject_cooldown(ticker)
                result = ExecutionResult(
                    intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=fill_price,
                    status="rejected", mode="live", broker_order_id=order_id,
                    reason=reject_msg, meta={"raw": state}, kind=intent_kind,
                )
                self._log(f"LIVE REJECT {ticker} orderId={order_id}: {reject_msg}")
                await event_bus.publish(self.robot_id, "order", {
                    "ticker": ticker, "side": side, "qty": qty, "price": fill_price,
                    "status": "rejected", "mode": "live", "orderId": order_id, "kind": intent.kind,
                    "reason": reject_msg,
                })
                return result

            self._log(f"LIVE FILL TIMEOUT {ticker} orderId={order_id}")
            await event_bus.publish(self.robot_id, "health", {
                "level": "warn",
                "message": "fill confirmation timeout",
                "ticker": ticker,
                "orderId": order_id,
            })
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=fill_price,
                status="submitted", mode="live", broker_order_id=order_id,
                reason="FILL_CONFIRM_TIMEOUT", meta={"raw": state}, kind=intent_kind,
            )
        except Exception as exc:
            logger.exception("live order failed robot=%s ticker=%s", self.robot_id, ticker)
            reject_msg = self._broker_reject_message(exc=exc)
            self._mark_reject_cooldown(ticker)
            self._log(f"LIVE ORDER ERROR {ticker}: {reject_msg}")
            await event_bus.publish(self.robot_id, "health", {
                "level": "error", "message": f"order failed: {reject_msg}", "ticker": ticker,
            })
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=fill_price,
                status="rejected", mode="live", reason=reject_msg, kind=intent_kind,
            )
        finally:
            self.guard.release(ticker)

    async def _execute_limit(
        self,
        intent: OrderIntent,
        *,
        ticker: str,
        side: str,
        qty: int,
        limit_price: float,
        intent_id: str,
        reduce_only: bool,
        intent_kind: str,
        last_price: float,
    ) -> ExecutionResult:
        existing = self._resting.get(ticker)
        if existing is not None and self._same_resting(
            existing, side=side, qty=qty, limit_price=limit_price,
        ):
            return self._resting_result(existing, reason="ALREADY_RESTING")
        # Broker-synced resting on same side/price (qty may already match after sync).
        if (
            existing is not None
            and existing.side == side.upper()
            and existing.broker_order_id
            and abs(float(existing.limit_price) - float(limit_price)) < 1e-6
        ):
            return self._resting_result(existing, reason="ALREADY_RESTING")

        if existing is not None:
            await self.cancel_resting(ticker)

        if self.mode == "paper":
            if self._limit_would_fill(side, last_price, limit_price):
                pnl = self.ledger.apply_fill(
                    ticker=ticker, side=side, quantity=qty, price=limit_price, reduce_only=reduce_only,
                )
                result = ExecutionResult(
                    intent_id=intent_id, ticker=ticker, side=side, quantity=qty,
                    price=limit_price, status="filled", mode="paper", pnl=pnl,
                    reason=intent.reason, kind=intent_kind,
                )
                self._log(
                    f"PAPER LIMIT FILL {side} {ticker} qty={qty} price={limit_price:.6g} "
                    f"kind={intent.kind} pnl={pnl:.4f}"
                )
                if not self.quiet:
                    await event_bus.publish(self.robot_id, "order", {
                        "ticker": ticker, "side": side, "qty": qty, "price": limit_price,
                        "status": "filled", "mode": "paper", "kind": intent.kind,
                    })
                return result

            ro = RestingOrder(
                intent_id=intent_id,
                ticker=ticker,
                side=side,
                quantity=qty,
                limit_price=limit_price,
                reduce_only=reduce_only,
                reason=intent.reason,
                kind=intent_kind,
            )
            self._resting[ticker] = ro
            self._log(f"PAPER LIMIT RESTING {side} {ticker} qty={qty} @ {limit_price:.6g}")
            if not self.quiet:
                await event_bus.publish(self.robot_id, "order", {
                    "ticker": ticker, "side": side, "qty": qty, "price": limit_price,
                    "status": "resting", "mode": "paper", "kind": intent.kind,
                })
            return self._resting_result(ro)

        if self.broker is None or not self.account_id:
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=limit_price,
                status="rejected", mode="live", reason="BROKER_OR_ACCOUNT_MISSING", kind=intent_kind,
            )

        adopted = await self._adopt_open_broker_limit(ticker, side=side)
        if adopted is not None:
            existing = adopted
            if self._same_resting(existing, side=side, qty=qty, limit_price=limit_price):
                return self._resting_result(existing, reason="ALREADY_RESTING")
            if (
                existing.side == side.upper()
                and abs(float(existing.limit_price) - float(limit_price)) < 1e-6
            ):
                return self._resting_result(existing, reason="ALREADY_RESTING")

        if not self.guard.try_acquire(ticker):
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=limit_price,
                status="rejected", mode="live", reason="IN_FLIGHT_ORDER", kind=intent_kind,
            )
        try:
            instrument = self._instrument_id(ticker)
            direction = "ORDER_DIRECTION_BUY" if side == "BUY" else "ORDER_DIRECTION_SELL"
            broker_type = getattr(self.broker, "broker_type", "")
            if broker_type == "bybit":
                direction = side
            if not self._tinvest_instrument_ready(instrument):
                self._log(f"LIVE LIMIT SKIP {ticker}: FIGI unresolved (got {instrument})")
                return ExecutionResult(
                    intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=limit_price,
                    status="rejected", mode="live", reason="FIGI_UNRESOLVED", kind=intent_kind,
                )
            endpoint = f"{broker_type or 'broker'}.post_order"
            started = datetime.now(timezone.utc)
            self._log(
                f"LIVE LIMIT submit {side} {ticker}→{instrument} qty={qty} "
                f"price={limit_price:.6g} dir={direction}"
            )
            try:
                resp = await self.broker.post_order(
                    instrument,
                    qty,
                    limit_price,
                    direction,
                    self.account_id,
                    reduce_only=reduce_only,
                )
                if broker_type != "bybit":
                    await log_external_api(
                        robot_id=self.robot_id,
                        user_id=self.user_id,
                        token_id=self.token_id,
                        endpoint=endpoint,
                        request_data={
                            "instrument": instrument,
                            "qty": qty,
                            "price": limit_price,
                            "direction": direction,
                            "account_id": self.account_id,
                            "reduce_only": reduce_only,
                        },
                        response_data=resp if isinstance(resp, dict) else {"raw": str(resp)},
                        response_status=200,
                        started_at=started,
                    )
            except Exception as exc:
                if broker_type != "bybit":
                    await log_external_api(
                        robot_id=self.robot_id,
                        user_id=self.user_id,
                        token_id=self.token_id,
                        endpoint=endpoint,
                        request_data={
                            "instrument": instrument,
                            "qty": qty,
                            "price": limit_price,
                            "direction": direction,
                            "account_id": self.account_id,
                        },
                        error_message=str(exc)[:500],
                        started_at=started,
                    )
                raise

            order_id = str(
                (resp or {}).get("order_id")
                or (resp or {}).get("orderId")
                or (resp or {}).get("orderLinkId")
                or ""
            ) or None
            await event_bus.publish(self.robot_id, "order", {
                "ticker": ticker, "side": side, "qty": qty, "price": limit_price,
                "status": "submitted", "mode": "live", "orderId": order_id, "kind": intent.kind,
            })
            if not order_id:
                ro = RestingOrder(
                    intent_id=intent_id,
                    ticker=ticker,
                    side=side,
                    quantity=qty,
                    limit_price=limit_price,
                    reduce_only=reduce_only,
                    reason=intent.reason,
                    kind=intent_kind,
                )
                self._resting[ticker] = ro
                return self._resting_result(ro, reason="NO_ORDER_ID")

            conf_status, conf_price, conf_qty, state = await self._await_fill(
                order_id,
                fallback_price=limit_price,
                fallback_qty=qty,
                timeout_sec=self.limit_fill_timeout_sec,
            )
            if conf_status == "filled":
                # Guard: sell LIMIT cannot fill meaningfully below limit (and vice versa).
                # Bad broker payloads previously caused "TP @ 2102" to book as market ~entry.
                bad_fill = False
                if conf_price > 0 and limit_price > 0:
                    if side == "SELL" and conf_price < limit_price * 0.995:
                        bad_fill = True
                    if side == "BUY" and conf_price > limit_price * 1.005:
                        bad_fill = True
                if bad_fill:
                    self._log(
                        f"LIVE LIMIT ignore bad fill {ticker}: fill={conf_price:.6g} "
                        f"limit={limit_price:.6g} — keep resting"
                    )
                    conf_status = "submitted"
                else:
                    pnl = self.ledger.apply_fill(
                        ticker=ticker, side=side, quantity=conf_qty, price=conf_price, reduce_only=reduce_only,
                    )
                    result = ExecutionResult(
                        intent_id=intent_id, ticker=ticker, side=side, quantity=conf_qty,
                        price=conf_price, status="filled", mode="live", pnl=pnl,
                        broker_order_id=order_id, reason=intent.reason,
                        meta={"raw": state, "orderType": "LIMIT"}, kind=intent_kind,
                    )
                    self._log(
                        f"LIVE LIMIT FILL {side} {ticker} qty={conf_qty} price={conf_price:.6g} "
                        f"orderId={order_id} kind={intent.kind} pnl={pnl:.4f}"
                    )
                    await event_bus.publish(self.robot_id, "order", {
                        "ticker": ticker, "side": side, "qty": conf_qty, "price": conf_price,
                        "status": "filled", "mode": "live", "orderId": order_id, "kind": intent.kind,
                    })
                    return result

            if conf_status == "rejected":
                reject_msg = self._broker_reject_message(state=state if isinstance(state, dict) else None)
                self._mark_reject_cooldown(ticker)
                return ExecutionResult(
                    intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=limit_price,
                    status="rejected", mode="live", broker_order_id=order_id,
                    reason=reject_msg, meta={"raw": state, "orderType": "LIMIT"}, kind=intent_kind,
                )

            ro = RestingOrder(
                intent_id=intent_id,
                ticker=ticker,
                side=side,
                quantity=qty,
                limit_price=limit_price,
                reduce_only=reduce_only,
                reason=intent.reason,
                kind=intent_kind,
                broker_order_id=order_id,
            )
            self._resting[ticker] = ro
            self.remember_broker_order_id(order_id)
            try:
                self._resting_submitted_at[ticker.upper()] = asyncio.get_running_loop().time()
            except RuntimeError:
                pass
            self._log(f"LIVE LIMIT RESTING {side} {ticker} qty={qty} @ {limit_price:.6g} orderId={order_id}")
            await event_bus.publish(self.robot_id, "order", {
                "ticker": ticker, "side": side, "qty": qty, "price": limit_price,
                "status": "resting", "mode": "live", "orderId": order_id, "kind": intent.kind,
            })
            return self._resting_result(ro)
        except Exception as exc:
            logger.exception("live limit order failed robot=%s ticker=%s", self.robot_id, ticker)
            reject_msg = self._broker_reject_message(exc=exc)
            self._mark_reject_cooldown(ticker)
            self._log(f"LIVE LIMIT ERROR {ticker}: {reject_msg}")
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=limit_price,
                status="rejected", mode="live", reason=reject_msg, kind=intent_kind,
            )
        finally:
            self.guard.release(ticker)

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
        intent_kind = str(getattr(intent, "kind", None) or "entry")
        order_type = str(getattr(intent, "order_type", None) or "MARKET").upper()

        if qty <= 0 or not ticker:
            return self._track_execution_result(ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=0,
                status="rejected", mode=self.mode, reason="INVALID_QTY_OR_TICKER", kind=intent_kind,
            ))

        mid = last_price
        if mid <= 0:
            return self._track_execution_result(ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=0,
                status="rejected", mode=self.mode, reason="STALE_OR_MISSING_PRICE", kind=intent_kind,
            ))

        if self._on_reject_cooldown(ticker):
            return ExecutionResult(
                intent_id=intent_id,
                ticker=ticker,
                side=side,
                quantity=qty,
                price=float(intent.price or mid),
                status="rejected",
                mode=self.mode,
                reason="REJECT_COOLDOWN",
                kind=intent_kind,
            )

        if self.mode == "paper":
            result = self.execute_intent_sync(intent, last_price=mid)
            if not self.quiet and result.status in ("filled", "resting"):
                await event_bus.publish(self.robot_id, "order", {
                    "ticker": ticker,
                    "side": side,
                    "qty": qty,
                    "price": result.price,
                    "status": result.status,
                    "mode": "paper",
                    "kind": intent.kind,
                })
            return result

        if self.mode == "live" and bid and ask and mid > 0:
            spread_pct = (ask - bid) / mid * 100.0
            if spread_pct > self.slippage_pct:
                await event_bus.publish(self.robot_id, "decision", {
                    "code": "SLIPPAGE_LIMIT_FALLBACK",
                    "ticker": ticker,
                    "spreadPct": spread_pct,
                })

        if order_type == "LIMIT":
            limit_price = float(intent.price or mid)
            return self._track_execution_result(await self._execute_limit(
                intent,
                ticker=ticker,
                side=side,
                qty=qty,
                limit_price=limit_price,
                intent_id=intent_id,
                reduce_only=reduce_only,
                intent_kind=intent_kind,
                last_price=mid,
            ))

        fill_price = float(intent.price or mid)
        if self.broker is None or not self.account_id:
            return ExecutionResult(
                intent_id=intent_id, ticker=ticker, side=side, quantity=qty, price=fill_price,
                status="rejected", mode="live", reason="BROKER_OR_ACCOUNT_MISSING", kind=intent_kind,
            )

        return self._track_execution_result(await self._execute_market_live(
            intent,
            ticker=ticker,
            side=side,
            qty=qty,
            fill_price=fill_price,
            intent_id=intent_id,
            reduce_only=reduce_only,
            intent_kind=intent_kind,
        ))


def attach_ticker_warnings(
    rows: list[dict[str, Any]],
    execution: ExecutionService | None,
    *,
    last_prices: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Copy position rows and attach `tickerWarning` when the ticker has a known issue."""
    if not rows:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        ticker = str(copy.get("ticker") or copy.get("figi") or "")
        warning: str | None = None
        quote: float | None = None
        if last_prices is not None:
            raw = last_prices.get(ticker.upper()) if ticker else None
            quote = float(raw) if raw is not None else 0.0
        if execution is not None:
            warning = execution.ticker_warning(ticker, last_price=quote)
        elif quote is not None and quote <= 0:
            warning = "Нет актуальной котировки"
        if warning:
            copy["tickerWarning"] = warning
        else:
            copy.pop("tickerWarning", None)
            copy.pop("ticker_warning", None)
        out.append(copy)
    return out
