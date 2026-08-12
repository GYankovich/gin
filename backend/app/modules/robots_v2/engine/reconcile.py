"""ADR-11 — broker portfolio → local shadow ledger reconciliation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.modules.robots.trading.broker_position_sync import extract_account_position_meta, money_to_float
from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots_v2.engine.event_bus import event_bus
from app.modules.robots_v2.engine.paper_ledger import PaperLedger, PaperPosition

logger = logging.getLogger(__name__)


@dataclass
class ReconcileResult:
    ok: bool
    cash: float = 0.0
    positions: int = 0
    diffs: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _pos_snapshot(ledger: PaperLedger) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for t, p in ledger.positions.items():
        out[t.upper()] = {
            "side": "LONG" if p.is_long else "SHORT",
            "quantity": int(p.quantity),
            "avgEntry": float(p.avg_entry_price),
        }
    return out


async def reconcile_from_broker(
    *,
    robot_id: int,
    broker: BrokerFacade,
    account_id: str,
    ledger: PaperLedger,
    instrument_map: dict[str, str],
    universe: list[str],
) -> ReconcileResult:
    """Overwrite shadow ledger from broker (source of truth). Never halts on diff."""
    try:
        portfolio = await broker.get_portfolio(account_id)
        free = await broker.get_free_funds(account_id)
    except Exception as exc:
        logger.exception("reconcile broker fetch failed robot=%s", robot_id)
        return ReconcileResult(ok=False, error=str(exc)[:500])

    positions_raw = []
    if isinstance(portfolio, dict):
        positions_raw = list(portfolio.get("positions") or portfolio.get("Positions") or [])
    meta = extract_account_position_meta(positions_raw)

    ticker_by_instr = {str(v).upper(): str(k).upper() for k, v in instrument_map.items()}
    allowed = {t.upper() for t in universe}

    before = _pos_snapshot(ledger)
    before_cash = float(ledger.cash)

    new_positions: dict[str, PaperPosition] = {}
    for key, row in meta.items():
        k = str(key).upper()
        ticker = ticker_by_instr.get(k)
        if ticker is None:
            if k in allowed or not allowed:
                ticker = k
            else:
                continue
        elif allowed and ticker not in allowed:
            continue
        qty = abs(int(round(float(row.get("qty") or 0))))
        if qty <= 0:
            continue
        avg = float(row.get("avg_price") or 0) or float(row.get("mark_price") or 0) or 1.0
        side = "SHORT" if float(row.get("qty") or 0) < 0 else "LONG"
        new_positions[ticker] = PaperPosition(
            ticker=ticker,
            side=side,
            quantity=qty,
            avg_entry_price=avg,
        )

    cash = float(free or 0.0)
    # If free funds missing, fall back to portfolio totals
    if cash <= 0 and isinstance(portfolio, dict):
        for key in ("totalAmountCurrencies", "total_amount_currencies", "available"):
            if key in portfolio:
                cash = money_to_float(portfolio.get(key))
                break

    ledger.replace_state(cash=cash, positions=new_positions)

    after = _pos_snapshot(ledger)
    diffs: list[dict[str, Any]] = []
    if abs(before_cash - cash) > 0.01:
        diffs.append({"field": "cash", "before": before_cash, "after": cash})
    all_tickers = set(before) | set(after)
    for t in sorted(all_tickers):
        b = before.get(t)
        a = after.get(t)
        if b != a:
            diffs.append({"field": "position", "ticker": t, "before": b, "after": a})

    result = ReconcileResult(ok=True, cash=cash, positions=len(new_positions), diffs=diffs)
    if diffs:
        await event_bus.publish(robot_id, "account", {
            "type": "account.reconciled",
            "cash": cash,
            "positions": len(new_positions),
            "diffs": diffs[:50],
            "at": datetime.now(timezone.utc).isoformat(),
        })
    return result
