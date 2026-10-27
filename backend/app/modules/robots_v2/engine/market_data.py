"""Market last prices for robots v2 paper cycles (MOEX + Bybit)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.moex.http_gate import moex_http_acquire
from app.modules.robots_v2.engine.live_bars import parse_moex_candle_begin
from app.modules.trading_core.contracts import Candle

logger = logging.getLogger(__name__)

_MOEX_TQBR_MARKETDATA = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
)
_MOEX_CANDLES = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker}/candles.json"
)


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
    wanted = [str(t).upper() for t in tickers if t]
    live: dict[str, float] = {}
    try:
        live = await fetch_moex_last_prices(wanted)
    except Exception as exc:
        logger.warning("MOEX ISS last prices failed: %s", exc)
    missing = [t for t in wanted if t not in live]
    if missing:
        for ticker, px in fetch_tqbr_prices(db, missing).items():
            live.setdefault(str(ticker).upper(), float(px))
    return live


def parse_moex_marketdata_last(payload: dict[str, Any], tickers: list[str]) -> dict[str, float]:
    """LAST from an ISS marketdata block. LCLOSEPRICE covers a quiet print."""
    wanted = {str(t).upper() for t in tickers if t}
    md = payload.get("marketdata") or {}
    cols = md.get("columns") or []
    idx = {str(name): i for i, name in enumerate(cols)}
    sec_i = idx.get("SECID")
    if sec_i is None:
        return {}
    price_indexes = [idx[name] for name in ("LAST", "LCLOSEPRICE", "MARKETPRICE") if name in idx]
    out: dict[str, float] = {}
    for row in md.get("data") or []:
        if sec_i >= len(row) or row[sec_i] is None:
            continue
        ticker = str(row[sec_i]).upper()
        if ticker not in wanted:
            continue
        for price_i in price_indexes:
            if price_i >= len(row) or row[price_i] is None:
                continue
            try:
                val = float(row[price_i])
            except (TypeError, ValueError):
                continue
            if val > 0:
                out[ticker] = val
                break
    return out


async def fetch_moex_last_prices(tickers: list[str]) -> dict[str, float]:
    """Live TQBR last prices for the robot universe. One ISS call."""
    wanted = [str(t).upper() for t in tickers if t]
    if not wanted:
        return {}
    params = {
        "iss.meta": "off",
        "iss.only": "marketdata",
        "securities": ",".join(wanted),
    }
    async with moex_http_acquire():
        async with httpx.AsyncClient(timeout=12, verify=False) as client:
            resp = await client.get(_MOEX_TQBR_MARKETDATA, params=params)
    if resp.status_code != 200:
        raise RuntimeError(f"MOEX ISS marketdata HTTP {resp.status_code}")
    return parse_moex_marketdata_last(resp.json(), wanted)


def parse_moex_candles_payload(payload: dict[str, Any], *, ticker: str, timeframe: str) -> list[Candle]:
    candles = payload.get("candles") or {}
    cols = candles.get("columns") or []
    idx = {str(name): i for i, name in enumerate(cols)}
    begin_i = idx.get("begin")
    if begin_i is None:
        return []
    out: list[Candle] = []
    for row in candles.get("data") or []:
        if begin_i >= len(row):
            continue
        opened = parse_moex_candle_begin(row[begin_i])
        if opened is None:
            continue

        def _num(name: str) -> float:
            i = idx.get(name)
            if i is None or i >= len(row) or row[i] is None:
                return 0.0
            try:
                return float(row[i])
            except (TypeError, ValueError):
                return 0.0

        close = _num("close")
        if close <= 0:
            continue
        vol_i = idx.get("volume")
        try:
            volume = int(row[vol_i]) if vol_i is not None and vol_i < len(row) and row[vol_i] is not None else 0
        except (TypeError, ValueError):
            volume = 0
        out.append(Candle(
            interval=timeframe,
            time=opened,
            open=_num("open") or close,
            high=_num("high") or close,
            low=_num("low") or close,
            close=close,
            volume=volume,
            secid=ticker.upper(),
        ))
    out.sort(key=lambda c: c.time)
    return out


async def fetch_moex_recent_candles(
    tickers: list[str],
    *,
    timeframe: str,
    interval: int,
    start: datetime,
    end: datetime,
) -> dict[str, list[Candle]]:
    """Closed TQBR candles for a short window. `begin` is converted from Moscow to UTC."""
    wanted = [str(t).upper() for t in tickers if t]
    if not wanted:
        return {}
    params = {
        "from": start.date().isoformat(),
        "till": end.date().isoformat(),
        "interval": int(interval),
        "iss.meta": "off",
    }

    async def _one(ticker: str) -> tuple[str, list[Candle]]:
        url = _MOEX_CANDLES.format(ticker=ticker)
        try:
            async with moex_http_acquire():
                async with httpx.AsyncClient(timeout=12, verify=False) as client:
                    resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("MOEX candles %s HTTP %s", ticker, resp.status_code)
                return ticker, []
            return ticker, parse_moex_candles_payload(resp.json(), ticker=ticker, timeframe=timeframe)
        except Exception as exc:
            logger.warning("MOEX candles %s failed: %s", ticker, exc)
            return ticker, []

    rows = await asyncio.gather(*[_one(t) for t in wanted])
    return {ticker: candles for ticker, candles in rows}


def rest_marks_to_store(
    *,
    seed_from_ws: bool,
    fetched: dict[str, float],
    gap_fill: dict[str, float],
) -> dict[str, float]:
    """What a cycle may write into ``last_prices``.

    Scalper ticks keep the websocket tape and only store names the stream
    missed. Poll cycles store every fresh REST print, including tickers that
    already had a price — otherwise the session freezes on the bootstrap print.
    """
    if seed_from_ws:
        source = gap_fill
    else:
        source = fetched
    out: dict[str, float] = {}
    for ticker, px in source.items():
        try:
            val = float(px)
        except (TypeError, ValueError):
            continue
        if val > 0:
            out[str(ticker).upper()] = val
    return out


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

    On poll cycles REST still overwrites SL/TP marks (vs a phantom WS spike).
    Strategy / break-even must still use :func:`strategy_tape_prices` so a
    delayed snapshot (PLZL 1020 vs tape ~1001) cannot pass the BE guard.
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


def strategy_tape_prices(
    rest_prices: dict[str, float],
    mark_prices: dict[str, float] | None,
) -> dict[str, float]:
    """Live tape wins over a delayed REST snapshot for strategy exits / BE.

    Poll cycles keep REST in ``rest_prices`` for SL/TP. ``mark_prices`` is the
    WS last-trade map. Using REST here is what let scalper reversal sell PLZL
    as if last were 1020 while the fill printed ~1000.
    """
    out = {str(t).upper(): float(px) for t, px in rest_prices.items() if px and float(px) > 0}
    for t, px in (mark_prices or {}).items():
        if px is None:
            continue
        try:
            val = float(px)
        except (TypeError, ValueError):
            continue
        if val > 0:
            out[str(t).upper()] = val
    return out


def poll_interval_seconds(raw: str) -> int:
    from app.modules.robots_v2.engine.types import poll_interval_seconds as _p
    return _p(raw)
