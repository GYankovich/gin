"""MOEX index composition provider with DB cache (ADR-06)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.moex.http_gate import moex_http_acquire

MOEX_INDEX_TICKERS_URL = "https://iss.moex.com/iss/index/{index_code}/tickers.json"


async def fetch_moex_index_tickers(
    index_code: str,
    *,
    as_of: date | None = None,
    robot_id: int | None = None,
    user_id: int | None = None,
    token_id: int | None = None,
) -> list[str]:
    code = str(index_code or "").strip().upper()
    url = MOEX_INDEX_TICKERS_URL.format(index_code=code)
    params: dict[str, Any] = {"iss.meta": "off", "limit": 500}
    if as_of is not None:
        params["date"] = as_of.isoformat()
    started = datetime.now(timezone.utc)
    status = None
    err: str | None = None
    out: list[str] = []
    try:
        async with moex_http_acquire():
            async with httpx.AsyncClient(timeout=20, verify=False) as client:
                resp = await client.get(url, params=params)
        status = int(resp.status_code)
        if resp.status_code != 200:
            err = f"HTTP {resp.status_code}"
            return []
        payload = resp.json()
        block = payload.get("tickers") or payload.get("analytics") or {}
        columns = block.get("columns") or []
        data = block.get("data") or []
        ticker_idx = None
        for i, col in enumerate(columns):
            if str(col).lower() in ("ticker", "secid", "securityid"):
                ticker_idx = i
                break
        if ticker_idx is None:
            return []
        for row in data:
            if not row or ticker_idx >= len(row):
                continue
            t = str(row[ticker_idx] or "").strip().upper()
            if t:
                out.append(t)
        out = sorted(set(out))
        return out
    except Exception as exc:
        err = str(exc)[:500]
        return []
    finally:
        if robot_id is not None:
            from app.modules.robots_v2.engine.session_log import log_external_api

            await log_external_api(
                robot_id=robot_id,
                user_id=user_id,
                token_id=token_id,
                endpoint=f"moex.iss.index/{code}/tickers",
                request_data={"index_code": code, "params": params},
                response_data={"count": len(out)} if not err else None,
                response_status=status,
                error_message=err,
                started_at=started,
            )


def _read_cache(db: Session, *, index_code: str, as_of: date, schema: str) -> list[str] | None:
    row = db.execute(
        text(f"""
            SELECT tickers FROM {schema}.moex_index_cache
            WHERE index_code = :index_code AND as_of_date = :as_of
        """),
        {"index_code": index_code.upper(), "as_of": as_of},
    ).fetchone()
    if not row:
        return None
    raw = row[0]
    if isinstance(raw, list):
        return [str(t).upper() for t in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return [str(t).upper() for t in parsed]
        except json.JSONDecodeError:
            return None
    return None


def _write_cache(db: Session, *, index_code: str, as_of: date, tickers: list[str], schema: str) -> None:
    db.execute(
        text(f"""
            INSERT INTO {schema}.moex_index_cache (index_code, as_of_date, tickers, fetched_at)
            VALUES (:index_code, :as_of, CAST(:tickers AS jsonb), :fetched_at)
            ON CONFLICT (index_code, as_of_date)
            DO UPDATE SET tickers = EXCLUDED.tickers, fetched_at = EXCLUDED.fetched_at
        """),
        {
            "index_code": index_code.upper(),
            "as_of": as_of,
            "tickers": json.dumps(sorted(set(tickers))),
            "fetched_at": datetime.now(timezone.utc),
        },
    )


async def resolve_moex_index_constituents(
    db: Session,
    *,
    index_code: str,
    as_of: date | None = None,
    schema: str = "public",
    use_cache: bool = True,
    robot_id: int | None = None,
    user_id: int | None = None,
    token_id: int | None = None,
) -> list[str]:
    code = str(index_code or "").strip().upper()
    trade_date = as_of or datetime.now(timezone.utc).date()
    if use_cache:
        cached = _read_cache(db, index_code=code, as_of=trade_date, schema=schema)
        if cached is not None:
            return cached
    tickers = await fetch_moex_index_tickers(
        code, as_of=trade_date, robot_id=robot_id, user_id=user_id, token_id=token_id,
    )
    if tickers:
        _write_cache(db, index_code=code, as_of=trade_date, tickers=tickers, schema=schema)
        db.commit()
    return tickers


async def resolve_crypto_index_constituents(
    db: Session,
    user_id: int,
    *,
    index_code: str,
    token_id: int | None = None,
    limit: int = 10,
    as_of: date | None = None,
) -> list[str]:
    code = str(index_code or "").strip().upper()
    if code != "TOP_BYBIT":
        return []
    if as_of is not None:
        from app.modules.robots.trading.pipeline.historical_liquidity import (
            list_bybit_symbols_from_cache,
            point_in_time_metrics,
        )
        symbols = list_bybit_symbols_from_cache(db)
        pit = point_in_time_metrics(
            db, tickers=symbols, as_of_date=as_of, lookback_days=20, market="bybit",
        )
        ranked = sorted(pit.items(), key=lambda kv: float(kv[1].get("avg_value") or 0), reverse=True)
        return [str(sym).upper() for sym, _ in ranked[:limit] if sym]

    from app.modules.robots.crypto_universe import _find_active_bybit_token, fetch_bybit_tickers

    token_row = _find_active_bybit_token(db, user_id, token_id=token_id)
    if not token_row:
        return []
    tickers = await fetch_bybit_tickers(
        api_key=token_row["token"],
        api_secret=token_row.get("token_secret") or "",
        testnet=bool(token_row.get("testnet", True)),
        category="linear",
    )
    ranked = sorted(
        tickers,
        key=lambda r: float(r.get("turnover24h") or r.get("volume24h") or 0),
        reverse=True,
    )
    out: list[str] = []
    for row in ranked[:limit]:
        sym = str(row.get("symbol") or row.get("ticker") or "").upper()
        if sym:
            out.append(sym)
    return out

async def list_index_metadata(
    db: Session,
    user_id: int,
    *,
    market: str,
    schema: str = "public",
) -> list[dict[str, Any]]:
    from app.modules.robots_v2.universe.presets import CRYPTO_INDICES, MOEX_INDICES

    items: list[dict[str, Any]] = []
    if market in ("moex", "all"):
        for meta in MOEX_INDICES:
            tickers = await resolve_moex_index_constituents(
                db, index_code=meta["code"], schema=schema, use_cache=True,
            )
            items.append({
                "code": meta["code"],
                "name": meta["name"],
                "constituentCount": len(tickers),
                "market": "moex",
            })
    if market in ("crypto", "all"):
        for meta in CRYPTO_INDICES:
            count = 10 if meta["code"] == "TOP_BYBIT" else 0
            items.append({
                "code": meta["code"],
                "name": meta["name"],
                "constituentCount": count,
                "market": "crypto",
            })
    return items
