"""Price-based realized PnL for audit fills (FIFO pairing, not ledger pnl)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


def enrich_fills_realized_pnl(
    fills: list[dict[str, Any]],
    *,
    commission_rate: float = 0.0005,
    tax_rate: float = 0.13,
    all_fills_chronological: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Add ``realizedPnl`` and ``netPnl`` to closing legs via FIFO; keep ``ledgerPnl``.

    ``realizedPnl`` = gross − entry/exit commission.
    ``netPnl`` = ``realizedPnl`` − tax on positive profit only (``tax_rate`` from config).

    When ``all_fills_chronological`` is provided (full history for pairing), PnL is
    computed on that timeline and mapped onto the paginated ``fills`` slice.
    """
    if not fills:
        return fills

    timeline = all_fills_chronological or sorted(
        fills,
        key=lambda f: (str(f.get("filledAt") or ""), str(f.get("id") or "")),
    )
    pnl_by_id = _fifo_realized_by_fill_id(
        timeline, commission_rate=commission_rate, tax_rate=tax_rate,
    )

    out: list[dict[str, Any]] = []
    for f in fills:
        row = dict(f)
        row["ledgerPnl"] = row.pop("pnl", None)
        fid = str(row.get("id") or "")
        pair = pnl_by_id.get(fid, (None, None, None))
        row["realizedPnl"] = pair[0]
        row["netPnl"] = pair[1]
        if pair[2] is not None:
            row["entryPrice"] = pair[2]
        out.append(row)
    return out


def _normalize_stored_fill_price(px: float, qty: float, *, ref_px: float | None = None) -> float:
    """Fix audit rows that stored notional (unit×qty) in the price column."""
    return normalize_fill_unit_price(px, qty, ref_px=ref_px)


def normalize_live_fill_price(
    px: float,
    qty: float,
    *,
    ref_px: float | None = None,
) -> float:
    """Per-share live fill from T-Invest ``executedOrderPrice``.

    That field is often the line notional (qty × last). Only two hypotheses:
    already a unit price, or notional / qty. Guessing qty-1 / qty+1 divisors
    plus a stale ref picks the wrong price (VKCO 1227/9=136.33 instead of 122.7).
    """
    if px <= 0:
        return px
    q = float(qty)
    if q <= 1.0 + 1e-9:
        return float(px)
    p = float(px)
    unit = p / q
    if ref_px is not None and ref_px > 0:
        rel_p = abs(p - ref_px) / ref_px
        rel_u = abs(unit - ref_px) / ref_px
        if rel_p <= 0.20:
            return p
        if rel_u <= 0.35:
            return unit
        return p if rel_p <= rel_u else unit
    if q >= 2 and p > 500 and unit < p * 0.45 and 0 < unit < 50_000:
        return unit
    return p


def normalize_fill_unit_price(
    px: float,
    qty: float,
    *,
    ref_px: float | None = None,
) -> float:
    """Return per-unit price; repair MOEX/T-Invest payloads that store line notional.

    Historical FIFO may see corrupt rows (notional stored against the wrong qty).
    Live order confirmation must use :func:`normalize_live_fill_price` instead.
    """
    if px <= 0:
        return px
    q = float(qty)
    if q <= 1.0 + 1e-9:
        return float(px)

    p = float(px)
    unit = p / q
    q_int = max(1, int(round(q)))
    candidates: list[float] = [p, unit]
    for div in range(max(1, q_int - 1), q_int + 4):
        if div > 1:
            candidates.append(p / div)

    if ref_px is not None and ref_px > 0:
        positive = [c for c in candidates if c > 0]
        if not positive:
            return p
        best = min(positive, key=lambda c: abs(c - ref_px))
        if abs(best - ref_px) / ref_px <= 0.35:
            return best
        return p if abs(p - ref_px) <= abs(unit - ref_px) else unit

    # No ref: divide only when stored value looks like line notional (large total).
    if q >= 2 and p > 500 and unit < p * 0.45 and 0 < unit < 50_000:
        return unit
    return p


def _unit_price_if_notional(px: float, qty: float, *, ref_px: float | None = None) -> float:
    """Fix broker payloads that stored notional (unit×qty) as price."""
    return _normalize_stored_fill_price(px, qty, ref_px=ref_px)


def _fifo_realized_by_fill_id(
    fills_chronological: list[dict[str, Any]],
    *,
    commission_rate: float,
    tax_rate: float,
) -> dict[str, tuple[float | None, float | None, float | None]]:
    """Map fill id → (realized PnL, net PnL, avg entry price for SELL legs)."""
    lots: dict[str, list[dict[str, float]]] = defaultdict(list)
    result: dict[str, tuple[float | None, float | None, float | None]] = {}

    for f in fills_chronological:
        fid = str(f.get("id") or "")
        ticker = str(f.get("ticker") or "").upper()
        side = str(f.get("side") or "").upper()
        qty = float(f.get("quantity") or 0)
        px = float(f.get("price") or 0)
        if not fid or not ticker or qty <= 0 or px <= 0:
            result[fid] = (None, None, None)
            continue

        if side == "BUY":
            lot_px = _normalize_stored_fill_price(px, qty)
            lots[ticker].append({"qty": qty, "px": lot_px, "orig_qty": qty})
            result[fid] = (None, None, None)
            continue

        if side != "SELL":
            result[fid] = (None, None, None)
            continue

        rem = qty
        gross = 0.0
        comm = 0.0
        matched = 0.0
        entry_cost = 0.0
        while rem > 1e-9 and lots[ticker]:
            lot = lots[ticker][0]
            take = min(rem, lot["qty"])
            entry_px = float(lot["px"])
            sell_px = _unit_price_if_notional(px, qty, ref_px=entry_px)
            gross += (sell_px - entry_px) * take
            comm += (entry_px + sell_px) * take * commission_rate
            entry_cost += entry_px * take
            matched += take
            rem -= take
            lot["qty"] -= take
            if lot["qty"] <= 1e-9:
                lots[ticker].pop(0)

        if matched <= 0:
            result[fid] = (None, None, None)
            continue
        realized = round(gross - comm, 4)
        tax = max(0.0, realized) * tax_rate
        net = round(realized - tax, 4)
        avg_entry = round(entry_cost / matched, 6)
        result[fid] = (realized, net, avg_entry)

    return result


def _leg_pnl(
    entry_px: float,
    sell_px: float,
    qty: float,
    *,
    commission_rate: float,
    tax_rate: float,
) -> tuple[float, float, float]:
    """Gross-after-commission, net-after-tax, and round-trip commission for one leg.

    Returns ``(realizedPnl, netPnl, commission)``.
    """
    gross = (sell_px - entry_px) * qty
    comm = round((entry_px + sell_px) * qty * commission_rate, 4)
    realized = round(gross - comm, 4)
    tax = max(0.0, realized) * tax_rate
    net = round(realized - tax, 4)
    return realized, net, comm


def build_round_trips(
    fills_chronological: list[dict[str, Any]],
    orders_by_id: dict[str, dict[str, Any]],
    exit_reasons: dict[tuple[str, str], str] | None = None,
    *,
    commission_rate: float = 0.0005,
    tax_rate: float = 0.13,
) -> list[dict[str, Any]]:
    """Pair BUY/SELL fills into round-trip rows for the orders table."""
    exit_reasons = exit_reasons or {}
    lots: dict[str, list[dict[str, Any]]] = defaultdict(list)
    trips: list[dict[str, Any]] = []

    for f in fills_chronological:
        ticker = str(f.get("ticker") or "").upper()
        side = str(f.get("side") or "").upper()
        qty = float(f.get("quantity") or 0)
        px = float(f.get("price") or 0)
        fid = str(f.get("id") or "")
        if not ticker or qty <= 0 or px <= 0:
            continue

        if side == "BUY":
            buy_px = _normalize_stored_fill_price(px, qty)
            buy_kind = str(f.get("kind") or f.get("reason") or "entry").strip() or "entry"
            lots[ticker].append({
                "buyFillId": fid,
                "buyAt": f.get("filledAt") or f.get("filled_at"),
                "buyPx": buy_px,
                "qty": qty,
                "origQty": qty,
                "entryReason": buy_kind,
            })
            continue

        if side != "SELL":
            continue

        order = orders_by_id.get(str(f.get("orderId") or f.get("order_id") or ""))
        rem = qty
        sell_at = f.get("filledAt") or f.get("filled_at")
        fill_kind = str(f.get("kind") or "")
        submitted_at = None
        if order:
            submitted_at = order.get("submittedAt") or order.get("submitted_at")

        while rem > 1e-9 and lots[ticker]:
            lot = lots[ticker][0]
            take = min(rem, float(lot["qty"]))
            entry_px = _unit_price_if_notional(
                float(lot["buyPx"]),
                float(lot.get("origQty") or lot["qty"]),
            )
            sell_px = _unit_price_if_notional(px, qty, ref_px=entry_px)
            realized_pnl, net_pnl, commission = _leg_pnl(
                entry_px, sell_px, take,
                commission_rate=commission_rate, tax_rate=tax_rate,
            )
            reason = _resolve_exit_reason(fill_kind, order, exit_reasons)
            listed_px = _listed_sell_price(order)
            trip_id = f"{fid}-{lot['buyFillId']}"
            trips.append({
                "id": trip_id,
                "ticker": ticker,
                "buyAt": lot["buyAt"],
                "buyPrice": round(entry_px, 6),
                "buyQty": take,
                "sellAt": sell_at,
                "sellListedPrice": listed_px,
                "sellFillPrice": round(sell_px, 6),
                "sellQty": take,
                "sellSubmittedAt": submitted_at,
                "status": "closed",
                "reason": reason,
                "entryReason": lot.get("entryReason") or "entry",
                "realizedPnl": realized_pnl,
                "netPnl": net_pnl,
                "commission": commission,
            })
            rem -= take
            lot["qty"] = float(lot["qty"]) - take
            if float(lot["qty"]) <= 1e-9:
                lots[ticker].pop(0)

    for ticker, queue in lots.items():
        for lot in queue:
            if float(lot["qty"]) <= 1e-9:
                continue
            trips.append({
                "id": str(lot["buyFillId"]),
                "ticker": ticker,
                "buyAt": lot["buyAt"],
                "buyPrice": round(float(lot["buyPx"]), 6),
                "buyQty": float(lot["qty"]),
                "sellAt": None,
                "sellListedPrice": None,
                "sellFillPrice": None,
                "sellQty": None,
                "sellSubmittedAt": None,
                "status": "open",
                "reason": "entry",
                "entryReason": lot.get("entryReason") or "entry",
                "realizedPnl": None,
                "netPnl": None,
                "commission": None,
            })

    trips.sort(
        key=lambda t: str(t.get("sellAt") or t.get("buyAt") or ""),
        reverse=True,
    )
    return trips


def _parse_trip_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def filter_round_trips_by_range(
    trips: list[dict[str, Any]],
    *,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Keep trips whose close (or open) time falls in half-open [from_at, to_at)."""
    if from_at is None and to_at is None:
        return trips
    out: list[dict[str, Any]] = []
    for trip in trips:
        ts = _parse_trip_ts(trip.get("sellAt") or trip.get("sell_at") or trip.get("buyAt") or trip.get("buy_at"))
        if ts is None:
            continue
        if from_at is not None and ts < from_at:
            continue
        if to_at is not None and ts >= to_at:
            continue
        out.append(trip)
    return out


def _listed_sell_price(order: dict[str, Any] | None) -> float | None:
    if not order:
        return None
    order_type = str(order.get("orderType") or order.get("order_type") or "MARKET").upper()
    price = order.get("price")
    if price is None:
        return None
    px = float(price)
    if px <= 0:
        return None
    if order_type == "MARKET":
        return None
    return round(px, 6)


def _resolve_exit_reason(
    fill_kind: str,
    order: dict[str, Any] | None,
    exit_reasons: dict[tuple[str, str], str],
) -> str:
    if order:
        cycle_id = str(order.get("cycleId") or order.get("cycle_id") or "")
        ticker = str(order.get("ticker") or "").upper()
        code = exit_reasons.get((cycle_id, ticker))
        if code:
            return code
        kind = str(order.get("kind") or "")
        if kind and kind not in ("entry", ""):
            return kind
    if fill_kind and fill_kind not in ("entry", ""):
        return fill_kind
    return "exit"


_GENERIC_ENTRY = frozenset({"", "entry"})
_GENERIC_EXIT = frozenset({"", "exit", "exit_strategy", "exit_sl_tp", "flatten", "eod_flatten"})


def _as_utc_ms(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.timestamp() * 1000.0
    raw = str(value).strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp() * 1000.0


def _nearest_signal_reason(
    signals: list[dict[str, Any]],
    *,
    side: str,
    at: Any,
    window_ms: float = 5 * 60 * 1000,
) -> str | None:
    """Closest strategy signal for ticker/side near ``at`` (default ±5 min)."""
    target = _as_utc_ms(at)
    if target is None or not signals:
        return None
    side_u = side.upper()
    best: tuple[float, str] | None = None
    for sig in signals:
        if str(sig.get("side") or "").upper() != side_u:
            continue
        reason = str(sig.get("reason") or sig.get("kind") or "").strip()
        if not reason or reason.lower() in _GENERIC_ENTRY | _GENERIC_EXIT:
            continue
        ts = _as_utc_ms(sig.get("createdAt") or sig.get("created_at"))
        if ts is None:
            continue
        dist = abs(ts - target)
        if dist > window_ms:
            continue
        if best is None or dist < best[0]:
            best = (dist, reason)
    return best[1] if best else None


def enrich_round_trips_with_signals(
    trips: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fill ``entryReason`` / refine exit ``reason`` from ``robots_v2_signals``.

    Fills historically store ``kind=entry`` / ``exit_strategy``; the real strategy
    code lives on signals (e.g. ``scalper_delta_cross``).
    """
    if not trips or not signals:
        return trips

    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sig in signals:
        ticker = str(sig.get("ticker") or "").upper()
        if ticker:
            by_ticker[ticker].append(sig)

    out: list[dict[str, Any]] = []
    for trip in trips:
        row = dict(trip)
        ticker = str(row.get("ticker") or "").upper()
        pool = by_ticker.get(ticker) or []
        entry = str(row.get("entryReason") or "").strip()
        if entry.lower() in _GENERIC_ENTRY:
            found = _nearest_signal_reason(pool, side="BUY", at=row.get("buyAt"))
            if found:
                row["entryReason"] = found
        reason = str(row.get("reason") or "").strip()
        if reason.lower() in _GENERIC_EXIT:
            found = (
                _nearest_signal_reason(pool, side="CLOSE", at=row.get("sellAt"))
                or _nearest_signal_reason(pool, side="SELL", at=row.get("sellAt"))
            )
            if found:
                row["reason"] = found
        out.append(row)
    return out
