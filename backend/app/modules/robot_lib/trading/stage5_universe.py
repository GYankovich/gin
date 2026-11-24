"""Stage5 live universe: today's accepted screening ∪ open positions (not full config dump)."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy import text
from sqlalchemy.orm import Session


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def collect_open_position_symbols(
    open_positions: Optional[Iterable[Dict[str, Any]]] = None,
    account_position_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[str]:
    """Trading symbols from DB open trades + broker meta (currency already excluded in meta)."""
    out: List[str] = []
    seen: Set[str] = set()

    def add(raw: Any) -> None:
        key = _norm(raw)
        if not key or key in seen:
            return
        seen.add(key)
        out.append(key)

    for pos in open_positions or []:
        add(pos.get("figi") or pos.get("ticker") or pos.get("symbol"))

    for key, meta in (account_position_meta or {}).items():
        try:
            qty = float((meta or {}).get("qty") or 0.0)
        except Exception:
            qty = 0.0
        if abs(qty) <= 1e-12:
            continue
        add(key)

    return out


def load_today_accepted_symbols(
    db: Session,
    schema: str,
    robot_id: int,
    *,
    is_crypto: bool,
    trade_date: Optional[date] = None,
    figi_by_ticker: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Accepted rows from crypto_universe_daily / daily_universe for trade_date (default today)."""
    td = trade_date or date.today()
    out: List[str] = []
    seen: Set[str] = set()

    def add(raw: Any) -> None:
        key = _norm(raw)
        if not key or key in seen:
            return
        seen.add(key)
        out.append(key)

    if is_crypto:
        rows = db.execute(
            text(
                f"""
                SELECT symbol
                FROM crypto_universe_daily
                WHERE robot_id = :rid AND trade_date = :td
                  AND LOWER(COALESCE(filter_result, '')) IN ('accept', 'accepted')
                ORDER BY created_at DESC
                LIMIT 1000
                """
            ),
            {"rid": int(robot_id), "td": td},
        ).fetchall()
        for r in rows or []:
            add(r[0])
        return out

    mapping = figi_by_ticker if isinstance(figi_by_ticker, dict) else {}
    rows = db.execute(
        text(
            f"""
            SELECT ticker
            FROM daily_universe
            WHERE robot_id = :rid AND trade_date = :td
              AND LOWER(COALESCE(filter_result, '')) IN ('accept', 'accepted')
            ORDER BY created_at DESC
            LIMIT 1000
            """
        ),
        {"rid": int(robot_id), "td": td},
    ).fetchall()
    for r in rows or []:
        ticker = _norm(r[0])
        if not ticker:
            continue
        mapped = _norm(
            mapping.get(ticker)
            or mapping.get(ticker.lower())
            or mapping.get(str(r[0]))
        )
        add(mapped or ticker)
    return out


def merge_stage5_figis(
    accepted_today: Sequence[str],
    open_symbols: Sequence[str],
) -> List[str]:
    """Union with open positions first (need exits), then today's accepted."""
    out: List[str] = []
    seen: Set[str] = set()
    for raw in list(open_symbols or []) + list(accepted_today or []):
        key = _norm(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


__all__ = [
    "collect_open_position_symbols",
    "load_today_accepted_symbols",
    "merge_stage5_figis",
]
