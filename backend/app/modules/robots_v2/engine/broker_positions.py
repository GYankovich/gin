"""Fetch / map broker portfolio positions for robots v2 (status + reconcile)."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.robots.trading.broker_position_sync import extract_account_position_meta, money_to_float
from app.modules.robots.trading.brokers.base import BrokerFacade
from app.modules.robots_v2.engine.paper_ledger import PaperPosition

logger = logging.getLogger(__name__)


@dataclass
class BrokerPositionsSnapshot:
    ok: bool
    cash: float = 0.0
    positions: list[dict[str, Any]] = field(default_factory=list)
    paper_positions: dict[str, PaperPosition] = field(default_factory=dict)
    error: str | None = None
    account_id: str | None = None


def map_broker_meta_to_positions(
    meta: dict[str, dict[str, Any]],
    *,
    instrument_map: dict[str, str],
    universe: list[str] | None = None,
    extra_tickers: set[str] | None = None,
) -> dict[str, PaperPosition]:
    """FIGI/ticker meta → PaperPosition keyed by ticker.

    Includes tickers in ``universe`` or ``extra_tickers`` (e.g. open robot fills).
    If both empty, includes all mapped positions.
    """
    ticker_by_instr = {str(v).upper(): str(k).upper() for k, v in instrument_map.items()}
    allowed = {t.upper() for t in (universe or [])}
    if extra_tickers:
        allowed |= {t.upper() for t in extra_tickers}

    new_positions: dict[str, PaperPosition] = {}
    for key, row in meta.items():
        k = str(key).upper()
        ticker = ticker_by_instr.get(k)
        if ticker is None:
            if not allowed or k in allowed:
                ticker = k
            else:
                continue
        elif allowed and ticker not in allowed:
            continue
        qty = abs(int(round(float(row.get("qty") or 0))))
        if qty <= 0:
            continue
        avg = float(row.get("avg_price") or 0) or float(row.get("mark_price") or 0) or 1.0
        mark = float(row.get("mark_price") or 0) or avg
        side = "SHORT" if float(row.get("qty") or 0) < 0 else "LONG"
        new_positions[ticker] = PaperPosition(
            ticker=ticker,
            side=side,
            quantity=qty,
            avg_entry_price=avg,
        )
        # stash mark on object for UI conversion
        setattr(new_positions[ticker], "_mark_price", mark)
    return new_positions


def paper_positions_to_rows(
    positions: dict[str, PaperPosition],
    *,
    prices: dict[str, float] | None = None,
    source: str = "broker",
) -> list[dict[str, Any]]:
    prices = prices or {}
    rows: list[dict[str, Any]] = []
    for t, p in positions.items():
        mark = prices.get(t)
        if mark is None:
            mark = float(getattr(p, "_mark_price", 0) or 0) or p.avg_entry_price
        row = p.to_dict(float(mark))
        row["source"] = source
        rows.append(row)
    return rows


def open_tickers_from_audit_fills(
    db: Session,
    *,
    robot_id: int,
    schema: str = "public",
) -> dict[str, datetime | None]:
    """FIFO net-open tickers from audit fills → ticker → last BUY filled_at."""
    rows = db.execute(
        text(f"""
            SELECT ticker, side, quantity, filled_at
            FROM {schema}.robots_v2_fills
            WHERE robot_id = :rid
            ORDER BY filled_at ASC
        """),
        {"rid": robot_id},
    ).fetchall()
    lots: dict[str, float] = defaultdict(float)
    last_buy_at: dict[str, datetime | None] = {}
    for row in rows:
        t = str(row.ticker or "").upper()
        if not t:
            continue
        q = float(row.quantity or 0)
        if str(row.side or "").upper() == "BUY":
            lots[t] += q
            last_buy_at[t] = row.filled_at
        else:
            lots[t] -= q
            if lots[t] <= 1e-9:
                lots[t] = 0.0
                last_buy_at.pop(t, None)
    return {t: last_buy_at.get(t) for t, q in lots.items() if q > 1e-9}


def apply_opened_at_hints(
    positions: dict[str, PaperPosition],
    hints: dict[str, datetime | None],
) -> None:
    for t, pos in positions.items():
        hint = hints.get(t.upper())
        if hint is not None:
            if getattr(hint, "tzinfo", None) is None:
                hint = hint.replace(tzinfo=timezone.utc)
            pos.opened_at = hint


async def fetch_broker_positions_snapshot(
    *,
    broker: BrokerFacade,
    account_id: str,
    instrument_map: dict[str, str],
    universe: list[str] | None = None,
    extra_tickers: set[str] | None = None,
) -> BrokerPositionsSnapshot:
    """Pull portfolio + free funds; map to PaperPosition / UI rows."""
    broker_type = getattr(broker, "broker_type", "broker")
    try:
        portfolio = await broker.get_portfolio(account_id)
        free = await broker.get_free_funds(account_id)
    except Exception as exc:
        logger.exception("broker positions fetch failed broker=%s", broker_type)
        return BrokerPositionsSnapshot(ok=False, error=str(exc)[:500], account_id=account_id)

    positions_raw: list[Any] = []
    if isinstance(portfolio, dict):
        positions_raw = list(portfolio.get("positions") or portfolio.get("Positions") or [])
    meta = extract_account_position_meta(positions_raw)
    paper = map_broker_meta_to_positions(
        meta,
        instrument_map=instrument_map,
        universe=universe,
        extra_tickers=extra_tickers,
    )

    cash = float(free or 0.0)
    if cash <= 0 and isinstance(portfolio, dict):
        for key in ("totalAmountCurrencies", "total_amount_currencies", "available"):
            if key in portfolio:
                cash = money_to_float(portfolio.get(key))
                break

    rows = paper_positions_to_rows(paper, source="broker")
    return BrokerPositionsSnapshot(
        ok=True,
        cash=cash,
        positions=rows,
        paper_positions=paper,
        account_id=account_id,
    )
