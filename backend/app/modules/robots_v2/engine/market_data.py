"""Market last prices for robots v2 paper cycles (MOEX + Bybit)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
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
    user_id: int | None = None,
    token_id: int | None = None,
    robot_id: int | None = None,
) -> dict[str, float]:
    """Last prices via Bybit tickers API — always logged to external_api_logs when ids provided."""
    if not tickers:
        return {}
    from app.modules.bybit.http_client import BybitHttpClient

    wanted = {t.upper() for t in tickers if t}
    client = BybitHttpClient(
        testnet=testnet,
        api_key=api_key,
        api_secret=api_secret or "",
        user_id=user_id,
        token_id=token_id,
        context_type="trading",
        context_ref=str(robot_id) if robot_id is not None else None,
    )
    started = datetime.now(timezone.utc)
    try:
        payload = await client.get_tickers(category=category)
        rows = list((payload.get("result") or {}).get("list") or [])
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
    except Exception:
        # BybitHttpClient already wrote external_api_logs on HTTP/API errors.
        raise
    finally:
        await client.close()
        _ = started


async def fetch_prices_for_session(
    db: Session,
    *,
    market: str,
    tickers: list[str],
    token_id: int,
    user_id: int,
    instrument_type: str = "stock",
    robot_id: int | None = None,
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
            user_id=user_id,
            token_id=token_id,
            robot_id=robot_id,
        )
    return fetch_tqbr_prices(db, tickers)


def merge_ws_and_rest_prices(
    *,
    last_prices: dict[str, float],
    rest_prices: dict[str, float],
    tickers: list[str],
    seed_from_ws: bool,
) -> tuple[dict[str, float], dict[str, float]]:
    """Split REST snapshot from live WS marks.

    On scalper ``price_tick`` (``seed_from_ws=True``) keep live WS marks and only
    REST-fill tickers the stream does not have. A delayed ``market_snapshot``
    overwriting WS is what let VKCO strategy-exits see 129.7 while the tape
    was ~122 — below break-even, but the guard used the stale print.

    On poll cycles REST still overwrites (SL/TP vs a phantom WS spike).
    ``gap_fill``: tickers missing from ``last_prices`` so the monitor is not
    frozen on a delayed snapshot.
    """
    trade: dict[str, float] = {}
    if seed_from_ws:
        trade = {t: last_prices[t] for t in tickers if t in last_prices}
        for t, px in rest_prices.items():
            if t in trade or px is None:
                continue
            try:
                val = float(px)
            except (TypeError, ValueError):
                continue
            if val > 0:
                trade[t] = val
    else:
        trade.update(rest_prices)
        for t in tickers:
            if t not in trade and t in last_prices:
                trade[t] = last_prices[t]
    gap_fill = {
        str(t).upper(): float(px)
        for t, px in rest_prices.items()
        if t not in last_prices and px is not None and float(px) > 0
    }
    return trade, gap_fill


def poll_interval_seconds(raw: str) -> int:
    from app.modules.robots_v2.engine.types import poll_interval_seconds as _p
    return _p(raw)
