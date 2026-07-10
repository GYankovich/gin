"""Архив ежедневного листинга MOEX (securities_listing): ISSUESIZE и др. по дате и доске.

Индекс: https://iss.moex.com/iss/archives/files/securities_listing_latest.json
Файлы: /iss/downloads/statistics/engines/stock/securitieslisting/securities_listing_<DATE>.csv.zip
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.modules.moex.http_gate import moex_http_acquire

logger = logging.getLogger(__name__)

LISTING_INDEX_URL = "https://iss.moex.com/iss/archives/files/securities_listing_latest.json"


def _parse_iss_block(payload: Dict[str, Any], key: str) -> Tuple[List[str], List[List[Any]]]:
    block = payload.get(key) or {}
    return list(block.get("columns") or []), list(block.get("data") or [])


def _find_listing_csv_zip_url(payload: Dict[str, Any], listing_date: date) -> Optional[str]:
    cols, data = _parse_iss_block(payload, "files")
    if not cols or not data:
        return None
    idx = {str(c): i for i, c in enumerate(cols)}
    d0 = listing_date.isoformat()

    def cell(row: List[Any], name: str) -> Any:
        i = idx.get(name)
        if i is None or i >= len(row):
            return None
        return row[i]

    for row in data:
        df = cell(row, "date_from")
        if df is None:
            continue
        ds = str(df)[:10]
        if ds != d0:
            continue
        ext = str(cell(row, "extension") or "").lower()
        if ext != "csv":
            continue
        url = cell(row, "url")
        if not url or not isinstance(url, str):
            continue
        if url.startswith("http"):
            return url
        return "https://iss.moex.com" + url
    return None


def _norm_header(h: str) -> str:
    return str(h or "").strip().upper().replace(" ", "_")


def _parse_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        x = float(str(v).replace(",", ".").replace(" ", ""))
        return x if x == x else None  # NaN
    except (TypeError, ValueError):
        return None


def _parse_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).replace(",", ".").replace(" ", "")))
    except (TypeError, ValueError):
        return None


def _parse_listing_csv_bytes(
        content: bytes,
        *,
        board: str,
) -> Dict[str, Dict[str, Any]]:
    """SECID (upper) → поля для merge в market_snapshot_data_history."""
    board_u = board.strip().upper()
    out: Dict[str, Dict[str, Any]] = {}
    text = None
    for enc in ("utf-8-sig", "cp1251"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return out
    sample = text[:5000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    for raw in reader:
        row = {_norm_header(k): (v if v != "" else None) for k, v in (raw or {}).items()}
        bid = str(row.get("BOARDID") or row.get("BOARD") or "").strip().upper()
        if bid != board_u:
            continue
        secid = str(row.get("SECID") or "").strip().upper()
        if not secid:
            continue
        issue = _parse_float(row.get("ISSUESIZE") or row.get("ISSUE_SIZE"))
        lot = _parse_int(row.get("LOTSIZE") or row.get("LOT_SIZE"))
        isin = row.get("ISIN")
        if isinstance(isin, str):
            isin = isin.strip() or None
        prev_leg = _parse_float(
            row.get("PREVLEGALCLOSEPRICE")
            or row.get("PREVPRICE")
            or row.get("PREVLEGALCLOSE")
            or row.get("PREV_CLOSE"),
        )
        rec: Dict[str, Any] = {}
        if issue is not None and issue > 0:
            rec["issue_size"] = float(issue)
        if lot is not None and lot > 0:
            rec["lot_size"] = int(lot)
        if isin:
            rec["isin"] = isin[:20]
        if prev_leg is not None and prev_leg > 0:
            rec["prev_legal_close_price"] = float(prev_leg)
        sn = row.get("SHORTNAME") or row.get("SECNAME")
        if isinstance(sn, str) and sn.strip():
            rec["short_name_listing"] = sn.strip()[:255]
        if rec:
            out[secid] = rec
    return out


async def load_listing_board_row_map(
        *,
        listing_date: date,
        board: str = "TQBR",
        timeout_sec: float = 120.0,
) -> Dict[str, Dict[str, Any]]:
    """Загрузить zip листинга за дату и вернуть карту SECID → справочные поля (для доски `board`)."""
    params = {"iss.meta": "off"}
    try:
        async with moex_http_acquire():
            async with httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=15.0, read=timeout_sec, write=30.0, pool=30.0),
                    verify=False,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; GIN-backend/1.0)",
                        "Accept": "application/json,*/*",
                        "Referer": "https://iss.moex.com/",
                    },
            ) as client:
                ir = await client.get(LISTING_INDEX_URL, params=params)
                if ir.status_code != 200:
                    logger.warning("listing index HTTP %s", ir.status_code)
                    return {}
                payload = ir.json()
                zip_url = _find_listing_csv_zip_url(payload, listing_date)
                if not zip_url:
                    logger.warning("listing index: no csv row for date=%s", listing_date.isoformat())
                    return {}
                zr = await client.get(zip_url)
                if zr.status_code != 200:
                    logger.warning("listing zip HTTP %s url=%s", zr.status_code, zip_url)
                    return {}
                raw = zr.content
        if len(raw) >= 4 and raw[:2] != b"PK":
            logger.warning("listing zip: non-zip body (len=%s), skip parse", len(raw))
            return {}
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            if not names:
                return {}
            inner = zf.read(names[0])
        return _parse_listing_csv_bytes(inner, board=board)
    except Exception as e:
        logger.warning("load_listing_board_row_map failed date=%s board=%s: %s", listing_date, board, e)
        return {}
