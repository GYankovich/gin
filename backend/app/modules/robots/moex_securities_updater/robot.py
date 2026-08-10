#///EPIC Modules.ITEM Module.TOPIC MoexSecuritiesUpdaterRobot [1]
"""Sync MOEX board listings into tqbr_securities (shares + bonds)."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.moex.http_gate import moex_http_acquire
from app.modules.robots.moex_securities_updater import queries

logger = logging.getLogger("robots.moex_securities")

ISS_COLUMNS = (
    "SECID,SHORTNAME,ISIN,SECNAME,REGNUMBER,FACEVALUE,MATDATE,"
    "CURRENCYID,LOTSIZE,STATUS,LISTLEVEL"
)
_UPSERT_BATCH = 200


def _parse_iss_block(payload: Dict[str, Any], key: str) -> Tuple[List[str], List[List[Any]]]:
    block = payload.get(key) or {}
    return list(block.get("columns") or []), list(block.get("data") or [])


def _cell(row: Sequence[Any], idx: Optional[int]) -> Any:
    if idx is None or idx < 0 or idx >= len(row):
        return None
    return row[idx]


def _as_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _as_upper(val: Any) -> Optional[str]:
    s = _as_str(val)
    return s.upper() if s else None


def _as_int(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _as_decimal(val: Any) -> Optional[Decimal]:
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _as_date(val: Any) -> Optional[date]:
    s = _as_str(val)
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _is_traded_from_status(status: Any) -> bool:
    s = _as_upper(status)
    if not s:
        return True
    # MOEX board STATUS: A = active, else treat as not traded.
    return s in {"A", "T", "1", "TRUE", "Y"}


async def _http_get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    async with moex_http_acquire():
        async with httpx.AsyncClient(timeout=45.0, verify=False) as client:
            resp = await client.get(url, params=params or {})
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} for {url}")
    return resp.json()


def _board_url(engine: str, market: str, board: str) -> str:
    return (
        f"https://iss.moex.com/iss/engines/{engine}/markets/{market}"
        f"/boards/{board}/securities.json"
    )


def _map_row(
    row: Sequence[Any],
    idx: Dict[str, int],
    *,
    engine: str,
    market: str,
    board: str,
    instrument_group: str,
    instrument_type: str,
) -> Optional[Dict[str, Any]]:
    secid = _as_upper(_cell(row, idx.get("SECID")))
    if not secid:
        return None
    status = _cell(row, idx.get("STATUS"))
    is_traded = _is_traded_from_status(status)
    currency = _as_upper(_cell(row, idx.get("CURRENCYID")))
    if currency == "SUR":
        currency = "RUB"
    return {
        "secid": secid,
        "shortname": _as_str(_cell(row, idx.get("SHORTNAME"))),
        "isin": _as_upper(_cell(row, idx.get("ISIN"))),
        "name": _as_str(_cell(row, idx.get("SECNAME"))),
        "regnumber": _as_str(_cell(row, idx.get("REGNUMBER"))),
        "instrument_type": instrument_type,
        "instrument_group": instrument_group,
        "engine": engine,
        "market": market,
        "primary_board": board,
        "is_traded": is_traded,
        "currency": currency,
        "face_value": _as_decimal(_cell(row, idx.get("FACEVALUE"))),
        "maturity_date": _as_date(_cell(row, idx.get("MATDATE"))),
        "lot_size": _as_int(_cell(row, idx.get("LOTSIZE"))),
        "issuer": None,
        "list_level": _as_int(_cell(row, idx.get("LISTLEVEL"))),
        "is_active": True,
        "extra_data_json": json.dumps(
            {"status": _as_str(status), "source": "moex_iss_board"},
            ensure_ascii=False,
        ),
    }


async def fetch_board_securities(
    *,
    engine: str,
    market: str,
    board: str,
    instrument_group: str,
    instrument_type: str,
) -> List[Dict[str, Any]]:
    url = _board_url(engine, market, board)
    params = {
        "iss.meta": "off",
        "iss.only": "securities",
        "securities.columns": ISS_COLUMNS,
        "securities.limit": 10000,
    }
    payload = await _http_get_json(url, params)
    cols, data = _parse_iss_block(payload, "securities")
    if not data:
        logger.warning("MOEX board %s/%s empty response", market, board)
        return []
    idx = {str(c).upper(): i for i, c in enumerate(cols)}
    out: List[Dict[str, Any]] = []
    for row in data:
        mapped = _map_row(
            row,
            idx,
            engine=engine,
            market=market,
            board=board,
            instrument_group=instrument_group,
            instrument_type=instrument_type,
        )
        if mapped:
            out.append(mapped)
    logger.info("MOEX board %s/%s fetched=%s", market, board, len(out))
    return out


def _upsert_batches(db: Session, rows: List[Dict[str, Any]]) -> int:
    total = 0
    for i in range(0, len(rows), _UPSERT_BATCH):
        chunk = rows[i : i + _UPSERT_BATCH]
        sql, params = queries.build_upsert_securities_batch(chunk)
        db.execute(text(sql), params)
        total += len(chunk)
    return total


async def sync_moex_securities_reference(db: Session) -> Dict[str, Any]:
    """Fetch TQBR/TQOB/TQCB and upsert into tqbr_securities; deactivate missing."""
    all_rows: List[Dict[str, Any]] = []
    boards = [b[2] for b in queries.MOEX_BOARDS]
    per_board: Dict[str, int] = {}

    for engine, market, board, group, itype in queries.MOEX_BOARDS:
        rows = await fetch_board_securities(
            engine=engine,
            market=market,
            board=board,
            instrument_group=group,
            instrument_type=itype,
        )
        per_board[board] = len(rows)
        all_rows.extend(rows)

    # Deduplicate by secid (prefer first occurrence / board order).
    by_secid: Dict[str, Dict[str, Any]] = {}
    for row in all_rows:
        by_secid.setdefault(row["secid"], row)
    unique_rows = list(by_secid.values())

    upserted = _upsert_batches(db, unique_rows) if unique_rows else 0

    seen = [r["secid"] for r in unique_rows]
    deactivated = 0
    if seen:
        sql, params = queries.build_deactivate_missing_query(boards=boards, seen_secids=seen)
        result = db.execute(text(sql), params)
        deactivated = int(result.rowcount or 0)

    summary = {
        "upserted": upserted,
        "unique": len(unique_rows),
        "deactivated": deactivated,
        "per_board": per_board,
    }
    logger.info("moex securities sync done: %s", summary)
    return summary
