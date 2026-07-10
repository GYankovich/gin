"""Загрузка OHLCV с MOEX ISS по тикеру (без FIGI)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.modules.moex.http_gate import moex_http_acquire

MOEX_HTTP_RETRIES = 3
MOEX_HTTP_TIMEOUT_SEC = 20


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _moex_get_json_with_retry(
        url: str,
        *,
        params: Optional[Dict[str, object]] = None,
        timeout: int = MOEX_HTTP_TIMEOUT_SEC,
        retries: int = MOEX_HTTP_RETRIES,
        context: str = "MOEX request",
) -> Dict[str, Any]:
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            async with moex_http_acquire():
                async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                    resp = await client.get(url, params=params)
            if resp.status_code != 200:
                raise RuntimeError(f"{context}: MOEX API error {resp.status_code} (попытка {attempt}/{retries})")
            return resp.json()
        except RuntimeError:
            raise
        except httpx.RequestError as e:
            last_exc = e
            if attempt < retries:
                await asyncio.sleep(0.35 * attempt)
    raise RuntimeError(f"{context}: не удалось подключиться к MOEX ISS") from last_exc


async def _resolve_board_and_market(security_id: str) -> Tuple[str, str]:
    meta_url = f"https://iss.moex.com/iss/securities/{security_id}.json"
    try:
        payload = await _moex_get_json_with_retry(
            meta_url,
            timeout=15,
            retries=2,
            context=f"MOEX metadata {security_id}",
        )
    except Exception:
        return "TQBR", "shares"
    boards = payload.get("boards", {})
    cols = boards.get("columns", []) or []
    data = boards.get("data", []) or []
    if not data or not cols:
        return "TQBR", "shares"
    idx = {name: i for i, name in enumerate(cols)}
    chosen = None
    for item in data:
        engine = str(item[idx["engine"]] if "engine" in idx else "")
        market = str(item[idx["market"]] if "market" in idx else "")
        primary = int(item[idx["is_primary"]] if "is_primary" in idx and item[idx["is_primary"]] is not None else 0)
        if engine == "stock" and market == "shares" and primary == 1:
            chosen = item
            break
    if chosen is None:
        for item in data:
            engine = str(item[idx["engine"]] if "engine" in idx else "")
            market = str(item[idx["market"]] if "market" in idx else "")
            if engine == "stock" and market == "shares":
                chosen = item
                break
    if chosen is None:
        chosen = data[0]
    board = str(chosen[idx["boardid"]] if "boardid" in idx else "TQBR")
    market = str(chosen[idx["market"]] if "market" in idx else "shares")
    return board, market


async def fetch_moex_candles_range(
        ticker: str,
        moex_interval: int,
        start: datetime,
        end: datetime,
        *,
        board_override: Optional[str] = None,
) -> List[Tuple[datetime, Decimal, Decimal, Decimal, Decimal, Optional[int]]]:
    """
    Возвращает список (bucket_start, open, high, low, close, volume).
    board_override: если задан (например TQBR), подставляется в URL после резолва market.
    """
    secid = ticker.strip().upper()
    if not secid:
        return []

    board, market = await _resolve_board_and_market(secid)
    if board_override:
        board = board_override.strip().upper()

    rows: List[Tuple[datetime, Decimal, Decimal, Decimal, Decimal, Optional[int]]] = []
    cur = _utc(start)
    end_u = _utc(end)
    while cur < end_u:
        chunk_end = min(end_u, cur + timedelta(days=365))
        url = f"https://iss.moex.com/iss/engines/stock/markets/{market}/boards/{board}/securities/{secid}/candles.json"
        start_offset = 0
        while True:
            params = {
                "from": cur.date().isoformat(),
                "till": chunk_end.date().isoformat(),
                "interval": moex_interval,
                "start": start_offset,
            }
            payload = await _moex_get_json_with_retry(
                url,
                params=params,
                timeout=MOEX_HTTP_TIMEOUT_SEC,
                retries=MOEX_HTTP_RETRIES,
                context=f"MOEX candles {secid} {cur.date()}..{chunk_end.date()}",
            )
            candles = payload.get("candles", {})
            cols = candles.get("columns", []) or []
            data = candles.get("data", []) or []
            if not data:
                break
            idx = {name: i for i, name in enumerate(cols)}
            for item in data:
                begin = item[idx["begin"]] if "begin" in idx else None
                if not begin:
                    continue
                ts = _utc(datetime.fromisoformat(str(begin).replace("Z", "+00:00")))
                o = Decimal(str(item[idx["open"]])) if "open" in idx and item[idx["open"]] is not None else Decimal(0)
                h = Decimal(str(item[idx["high"]])) if "high" in idx and item[idx["high"]] is not None else o
                l = Decimal(str(item[idx["low"]])) if "low" in idx and item[idx["low"]] is not None else o
                c = Decimal(str(item[idx["close"]])) if "close" in idx and item[idx["close"]] is not None else o
                vol = int(item[idx["volume"]]) if "volume" in idx and item[idx["volume"]] is not None else None
                rows.append((ts, o, h, l, c, vol))
            if len(data) < 500:
                break
            start_offset += len(data)
        cur = chunk_end
    return rows
