"""ADR-11 — broker portfolio → local shadow ledger reconciliation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots_v2.engine.broker_positions import (
    fetch_broker_positions_snapshot,
    map_broker_meta_to_positions,
)
from app.modules.robots_v2.engine.event_bus import event_bus
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.engine.session_log import log_external_api

logger = logging.getLogger(__name__)


@dataclass
class ReconcileResult:
    ok: bool
    cash: float = 0.0
    positions: int = 0
    diffs: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    adopted: list[str] = field(default_factory=list)


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
    user_id: int | None = None,
    token_id: int | None = None,
    extra_tickers: set[str] | None = None,
) -> ReconcileResult:
    """Overwrite shadow ledger from broker (source of truth). Neverhalts on diff."""
    broker_type = getattr(broker, "broker_type", "broker")
    try:
        started = datetime.now(timezone.utc)
        snap = await fetch_broker_positions_snapshot(
            broker=broker,
            account_id=account_id,
            instrument_map=instrument_map,
            universe=universe,
            extra_tickers=extra_tickers,
        )
        if broker_type != "bybit":
            await log_external_api(
                robot_id=robot_id,
                user_id=user_id,
                token_id=token_id,
                endpoint=f"{broker_type}.get_portfolio",
                request_data={"account_id": account_id},
                response_data={"positions": snap.positions and len(snap.positions)},
                response_status=200 if snap.ok else None,
                error_message=snap.error,
                started_at=started,
            )
            await log_external_api(
                robot_id=robot_id,
                user_id=user_id,
                token_id=token_id,
                endpoint=f"{broker_type}.get_free_funds",
                request_data={"account_id": account_id},
                response_data={"free": snap.cash if snap.ok else None},
                response_status=200 if snap.ok else None,
                error_message=None if snap.ok else snap.error,
                started_at=started,
            )
    except Exception as exc:
        logger.exception("reconcile broker fetch failed robot=%s", robot_id)
        if broker_type != "bybit":
            await log_external_api(
                robot_id=robot_id,
                user_id=user_id,
                token_id=token_id,
                endpoint=f"{broker_type}.reconcile",
                request_data={"account_id": account_id},
                error_message=str(exc)[:500],
            )
        return ReconcileResult(ok=False, error=str(exc)[:500])

    if not snap.ok:
        return ReconcileResult(ok=False, error=snap.error)

    before = _pos_snapshot(ledger)
    before_cash = float(ledger.cash)
    new_positions = snap.paper_positions
    cash = float(snap.cash)

    # Prefer mapper path already filled; keep type consistent
    if not isinstance(new_positions, dict):
        new_positions = map_broker_meta_to_positions(
            {},
            instrument_map=instrument_map,
            universe=universe,
            extra_tickers=extra_tickers,
        )

    # Broker remaps create fresh PaperPosition(opened_at=now) every sync.
    # Preserve prior open time so min_hold / LIMIT TP are not reset forever.
    for t, pos in list(new_positions.items()):
        key = str(t).upper()
        old = ledger.positions.get(key)
        if old is None:
            continue
        if str(getattr(old, "side", "")).upper() != str(getattr(pos, "side", "")).upper():
            continue
        old_opened = getattr(old, "opened_at", None)
        if old_opened is not None:
            pos.opened_at = old_opened

    ledger.replace_state(cash=cash, positions=new_positions)

    after = _pos_snapshot(ledger)
    diffs: list[dict[str, Any]] = []
    if abs(before_cash - cash) > 0.01:
        diffs.append({"field": "cash", "before": before_cash, "after": cash})
    all_tickers = set(before) | set(after)
    adopted: list[str] = []
    for t in sorted(all_tickers):
        b = before.get(t)
        a = after.get(t)
        if b != a:
            diffs.append({"field": "position", "ticker": t, "before": b, "after": a})
        if b is None and a is not None:
            adopted.append(t)

    result = ReconcileResult(
        ok=True,
        cash=cash,
        positions=len(new_positions),
        diffs=diffs,
        adopted=adopted,
    )
    if diffs:
        await event_bus.publish(robot_id, "account", {
            "type": "account.reconciled",
            "cash": cash,
            "positions": len(new_positions),
            "adopted": adopted,
            "diffs": diffs[:50],
            "at": datetime.now(timezone.utc).isoformat(),
        })
    return result
