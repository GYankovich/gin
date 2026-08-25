"""Normalize broker GetOrders rows and filter robot-relevant open orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.robots.trading.broker_position_sync import money_to_float

_ACTIVE_STATUSES = frozenset({
    "EXECUTION_REPORT_STATUS_NEW",
    "EXECUTION_REPORT_STATUS_PARTIALLYFILL",
    "EXECUTION_REPORT_STATUS_PARTIAL_FILL",
    "NEW",
    "PARTIALLYFILLED",
    "PARTIAL_FILL",
    "PARTIALLY_FILLED",
    "ACTIVE",
    "OPEN",
    "CREATED",
    "PENDINGNEW",
    "PENDING_NEW",
    "UNTRIGGERED",
})
_FILL_STATUSES = frozenset({
    "EXECUTION_REPORT_STATUS_FILL",
    "FILL",
    "FILLED",
})
_CANCEL_STATUSES = frozenset({
    "EXECUTION_REPORT_STATUS_CANCELLED",
    "EXECUTION_REPORT_STATUS_CANCELED",
    "CANCELLED",
    "CANCELED",
})
_REJECT_STATUSES = frozenset({
    "EXECUTION_REPORT_STATUS_REJECTED",
    "REJECTED",
})


@dataclass(frozen=True)
class NormalizedBrokerOrder:
    order_id: str
    ticker: str
    instrument_id: str
    side: str  # BUY | SELL
    quantity: int
    limit_price: float
    filled_qty: float
    status_raw: str
    lifecycle: str  # active | filled | cancelled | rejected | unknown
    order_type: str  # LIMIT | MARKET | UNKNOWN
    reduce_only: bool = False


def classify_order_lifecycle(status_raw: str) -> str:
    s = str(status_raw or "").upper().replace(" ", "")
    if not s:
        return "unknown"
    if s in _FILL_STATUSES or (s.endswith("FILL") and "PARTIAL" not in s and "CANCEL" not in s):
        return "filled"
    if s in _CANCEL_STATUSES or s.endswith("CANCELLED") or s.endswith("CANCELED"):
        return "cancelled"
    if s in _REJECT_STATUSES or s.endswith("REJECTED"):
        return "rejected"
    if s in _ACTIVE_STATUSES or "NEW" in s or "PARTIAL" in s:
        return "active"
    return "unknown"


def _normalize_side(raw: Any) -> str:
    s = str(raw or "").upper()
    if "BUY" in s or s == "B":
        return "BUY"
    if "SELL" in s or s == "S":
        return "SELL"
    return s or "SELL"


def _normalize_order_type(raw: Any) -> str:
    s = str(raw or "").upper()
    if "LIMIT" in s:
        return "LIMIT"
    if "MARKET" in s:
        return "MARKET"
    return "UNKNOWN"


def normalize_broker_order_row(
    row: dict[str, Any],
    *,
    instrument_map: dict[str, str] | None = None,
) -> NormalizedBrokerOrder | None:
    """Map T-Invest / Bybit GetOrders row → NormalizedBrokerOrder."""
    if not isinstance(row, dict):
        return None
    oid = str(row.get("orderId") or row.get("order_id") or row.get("id") or "").strip()
    if not oid:
        return None

    instr = str(
        row.get("figi")
        or row.get("instrumentUid")
        or row.get("instrument_uid")
        or row.get("symbol")
        or ""
    ).strip().upper()
    ticker_hint = str(row.get("ticker") or "").strip().upper()

    ticker_by_instr = {
        str(v).upper(): str(k).upper()
        for k, v in (instrument_map or {}).items()
    }
    ticker = ticker_hint or ticker_by_instr.get(instr) or instr
    if not ticker:
        return None

    qty = money_to_float(
        row.get("lotsRequested")
        or row.get("lots_requested")
        or row.get("quantity")
        or row.get("qty")
        or 0
    )
    filled = money_to_float(
        row.get("lotsExecuted")
        or row.get("lots_executed")
        or row.get("filled_qty")
        or row.get("cumExecQty")
        or 0
    )
    price = money_to_float(
        row.get("initialOrderPrice")
        or row.get("initialSecurityPrice")
        or row.get("price")
        or row.get("limitPrice")
        or row.get("avg_price")
        or 0
    )
    status_raw = str(
        row.get("executionReportStatus") or row.get("status") or row.get("orderStatus") or ""
    )
    side = _normalize_side(row.get("direction") or row.get("side"))
    order_type = _normalize_order_type(row.get("orderType") or row.get("order_type"))
    reduce_only = bool(row.get("reduceOnly") or row.get("reduce_only") or False)

    return NormalizedBrokerOrder(
        order_id=oid,
        ticker=ticker,
        instrument_id=instr or ticker,
        side=side,
        quantity=max(0, int(round(qty))),
        limit_price=float(price or 0),
        filled_qty=float(filled or 0),
        status_raw=status_raw,
        lifecycle=classify_order_lifecycle(status_raw),
        order_type=order_type,
        reduce_only=reduce_only,
    )


def normalize_broker_orders(
    rows: list[Any] | None,
    *,
    instrument_map: dict[str, str] | None = None,
) -> list[NormalizedBrokerOrder]:
    out: list[NormalizedBrokerOrder] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        norm = normalize_broker_order_row(row, instrument_map=instrument_map)
        if norm is not None:
            out.append(norm)
    return out


def filter_robot_scope_orders(
    orders: list[NormalizedBrokerOrder],
    *,
    position_tickers: set[str],
    known_order_ids: set[str],
) -> list[NormalizedBrokerOrder]:
    """Keep orders we own (known id) or that sit on held tickers."""
    pos = {str(t).upper() for t in position_tickers}
    known = {str(x).strip() for x in known_order_ids if x}
    out: list[NormalizedBrokerOrder] = []
    for o in orders:
        if o.order_id in known or o.ticker.upper() in pos:
            out.append(o)
    return out


def pick_resting_per_ticker(
    active_orders: list[NormalizedBrokerOrder],
    *,
    prefer_order_ids: set[str] | None = None,
) -> dict[str, NormalizedBrokerOrder]:
    """One active LIMIT (or unknown-type) order per ticker for local resting map."""
    prefer = {str(x) for x in (prefer_order_ids or set()) if x}
    by_ticker: dict[str, list[NormalizedBrokerOrder]] = {}
    for o in active_orders:
        if o.lifecycle != "active":
            continue
        if o.order_type == "MARKET":
            continue
        if o.quantity <= 0:
            continue
        by_ticker.setdefault(o.ticker.upper(), []).append(o)

    chosen: dict[str, NormalizedBrokerOrder] = {}
    for ticker, group in by_ticker.items():
        preferred = [o for o in group if o.order_id in prefer]
        pool = preferred or group
        # Prefer SELL (TP/exit for longs), then highest limit price for sells.
        pool_sorted = sorted(
            pool,
            key=lambda o: (
                0 if o.side == "SELL" else 1,
                -float(o.limit_price or 0),
                o.order_id,
            ),
        )
        chosen[ticker] = pool_sorted[0]
    return chosen
