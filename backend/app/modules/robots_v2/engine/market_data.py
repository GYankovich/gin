"""Market last prices for robots v2 paper cycles (MOEX + Bybit)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def fetch_tqbr_prices(db: Session, tickers: list[str]) -> dict[str, float]:
    if not tickers:
        return {}
    upper = [t.upper() for t in tickers]
    snap = db.execute(
        text("""
            SELECT id FROM market_snapshot
            WHERE board = 'TQBR' AND status = 'SUCCESS'
            ORDER BY snapshot_time DESC LIMIT 1
        """),
    ).fetchone()
    if not snap:
        return {}
    placeholders = ", ".join(f":t{i}" for i in range(len(upper)))
    params: dict[str, Any] = {"sid": int(snap[0])}
    for i, t in enumerate(upper):
        params[f"t{i}"] = t
    rows = db.execute(
        text(f"""
            SELECT ticker, last_price FROM market_snapshot_data
            WHERE snapshot_id = :sid AND ticker IN ({placeholders})
        """),
        params,
    ).fetchall()
    return {str(r[0]).upper(): float(r[1]) for r in rows if r[1] is not None}


async def fetch_bybit_prices(
    *,
    api_key: str,
    api_secret: str,
    testnet: bool,
    tickers: list[str],
    category: str = "linear",
) -> dict[str, float]:
    """Last prices for selected symbols via Bybit tickers API (cached category dump)."""
    if not tickers:
        return {}
    from app.modules.robots.crypto_universe import fetch_bybit_tickers

    wanted = {t.upper() for t in tickers if t}
    rows = await fetch_bybit_tickers(
        api_key=api_key,
        api_secret=api_secret or "",
        testnet=testnet,
        category=category,
    )
    out: dict[str, float] = {}
    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        if sym not in wanted:
            continue
        px = row.get("lastPrice")
        if px is None:
            px = row.get("markPrice")
        try:
            val = float(px or 0)
        except (TypeError, ValueError):
            continue
        if val > 0:
            out[sym] = val
    return out


async def fetch_prices_for_session(
    db: Session,
    *,
    market: str,
    tickers: list[str],
    token_id: int,
    user_id: int,
    instrument_type: str = "stock",
) -> dict[str, float]:
    if market == "crypto":
        from app.modules.robots_v2.universe.token_context import load_token_context

        ctx = load_token_context(
            db,
            user_id=user_id,
            token_id=token_id,
            instrument_type=instrument_type,
        )
        if not ctx.api_key:
            logger.warning("bybit prices skipped: missing api_key token_id=%s", token_id)
            return {}
        category = "inverse" if instrument_type == "coin_futures" else "linear"
        return await fetch_bybit_prices(
            api_key=ctx.api_key,
            api_secret=ctx.api_secret or "",
            testnet=ctx.testnet,
            tickers=tickers,
            category=category,
        )
    return fetch_tqbr_prices(db, tickers)


def poll_interval_seconds(raw: str) -> int:
    from app.modules.robots_v2.engine.types import poll_interval_seconds as _p
    return _p(raw)
