"""Point-in-time MOEX board membership (no live listing look-ahead)."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.moex.http_gate import moex_http_acquire

logger = logging.getLogger(__name__)

_HISTORY_SPEC: dict[str, tuple[str, str]] = {
    "TQBR": ("stock", "shares"),
    "TQTF": ("stock", "shares"),
    "TQOB": ("stock", "bonds"),
    "TQCB": ("stock", "bonds"),
    "RFUD": ("futures", "forts"),
}


def _history_url(board: str) -> str:
    b = board.strip().upper() or "TQBR"
    engine, market = _HISTORY_SPEC.get(b, ("stock", "shares"))
    return (
        f"https://iss.moex.com/iss/history/engines/{engine}/markets/{market}"
        f"/boards/{b}/securities.json"
    )


async def fetch_moex_board_secids_on_day(board: str, day: date) -> list[str]:
    """SECIDs that had a history row on ``day`` (empty on weekends/holidays)."""
    url = _history_url(board)
    out: list[str] = []
    start = 0
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        for _ in range(40):
            params = {"iss.meta": "off", "date": day.isoformat(), "start": start, "limit": 100}
            async with moex_http_acquire():
                resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("board history HTTP %s board=%s day=%s", resp.status_code, board, day)
                break
            payload = resp.json() if resp.content else {}
            block = payload.get("history") or {}
            cols = [str(c) for c in (block.get("columns") or [])]
            rows = block.get("data") or []
            if not rows:
                break
            try:
                secid_i = cols.index("SECID")
            except ValueError:
                secid_i = 0
            for row in rows:
                if not row or secid_i >= len(row):
                    continue
                t = str(row[secid_i] or "").strip().upper()
                if t and t not in seen:
                    seen.add(t)
                    out.append(t)
            if len(rows) < 100:
                break
            start += len(rows)
    return out


async def list_moex_board_tickers_as_of(
    board: str,
    as_of: date,
    *,
    lookback_days: int = 12,
) -> list[str]:
    """Nearest session on or before ``as_of`` (skip weekends/holidays)."""
    for i in range(max(1, lookback_days)):
        day = as_of - timedelta(days=i)
        tickers = await fetch_moex_board_secids_on_day(board, day)
        if tickers:
            return tickers
    return []


def list_moex_symbols_from_cache(
    db: Session,
    *,
    as_of: date,
    market: str = "moex",
) -> list[str]:
    """Tickers that already have candles strictly before as_of (causal fallback)."""
    end = datetime.combine(as_of, time.min, tzinfo=timezone.utc)
    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT instrument_id
            FROM candles_cache
            WHERE LOWER(market) = :market
              AND candle_time < :end
            ORDER BY instrument_id
            """
        ),
        {"market": str(market or "moex").strip().lower(), "end": end},
    ).fetchall()
    return [str(r[0]).strip().upper() for r in rows if r and r[0]]
