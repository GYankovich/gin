"""Corporate actions: MOEX-sourced dividend rows (ETL) and DB upsert."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.scheduler_utils import scheduler_startup_delay
from app.modules.moex.http_gate import moex_http_acquire

logger = logging.getLogger(__name__)

CCI_MAX_PAGES = 150


def _bulk_upsert_tqbr_securities(
    db: Session,
    schema: str,
    batch: List[Tuple[str, Optional[str], Optional[str]]],
) -> int:
    """Один INSERT … VALUES (…), (…) … ON CONFLICT вместо построчных execute."""
    if not batch:
        return 0
    by_secid: Dict[str, Tuple[str, Optional[str], Optional[str]]] = {}
    for secid, sn, isin in batch:
        by_secid[secid] = (secid, sn, isin)
    rows = list(by_secid.values())
    parts: List[str] = []
    params: Dict[str, Any] = {}
    for i, (secid, sn, isin) in enumerate(rows):
        parts.append(f"(:secid_{i}, :sn_{i}, :isin_{i}, CURRENT_TIMESTAMP)")
        params[f"secid_{i}"] = secid
        params[f"sn_{i}"] = sn
        params[f"isin_{i}"] = isin
    sql = f"""
        INSERT INTO {schema}.tqbr_securities (secid, shortname, isin, updated_at)
        VALUES {", ".join(parts)}
        ON CONFLICT (secid) DO UPDATE SET
            shortname = EXCLUDED.shortname,
            isin = EXCLUDED.isin,
            updated_at = CURRENT_TIMESTAMP
    """
    db.execute(text(sql), params)
    return len(rows)


CCI_URL = "https://iss.moex.com/iss/cci/corp-actions/dividends.json"


def _parse_iss_block(payload: Dict[str, Any], key: str) -> Tuple[List[str], List[List[Any]]]:
    block = payload.get(key) or {}
    return list(block.get("columns") or []), list(block.get("data") or [])


async def _http_get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    async with moex_http_acquire():
        async with httpx.AsyncClient(timeout=25.0, verify=False) as client:
            resp = await client.get(url, params=params or {})
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} for {url}")
    return resp.json()


async def fetch_cci_dividends_page(
        *,
        updated_after: Optional[datetime] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        start: int = 0,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"iss.meta": "off", "start": start}
    if updated_after:
        params["updated_after"] = updated_after.strftime("%Y-%m-%d %H:%M:%S")
    if date_from:
        params["date_from"] = date_from.isoformat()
    if date_to:
        params["date_to"] = date_to.isoformat()
    return await _http_get_json(CCI_URL, params)


async def fetch_security_dividends_json(secid: str) -> Dict[str, Any]:
    url = f"https://iss.moex.com/iss/securities/{secid.upper()}/dividends.json"
    return await _http_get_json(url, {"iss.meta": "off"})


def upsert_equity_dividend_row(
        db: Session,
        *,
        source: str,
        external_corp_action_id: str,
        secid: str,
        ticker: str,
        ex_date: date,
        amount_per_share: Optional[Decimal],
        currency: Optional[str],
        source_updated_at: Optional[datetime],
        raw_payload: Dict[str, Any],
) -> None:
    schema = settings.DB_SCHEMA
    db.execute(
        text(f"""
            INSERT INTO {schema}.equity_dividend_events
                (source, external_corp_action_id, secid, ticker, ex_date,
                 amount_per_share, currency, source_updated_at, raw_payload)
            VALUES
                (:source, :ext_id, :secid, :ticker, :ex_date,
                 :amount, :currency, :src_upd, CAST(:raw AS jsonb))
            ON CONFLICT (source, external_corp_action_id) DO UPDATE SET
                secid = EXCLUDED.secid,
                ticker = EXCLUDED.ticker,
                ex_date = EXCLUDED.ex_date,
                amount_per_share = EXCLUDED.amount_per_share,
                currency = EXCLUDED.currency,
                source_updated_at = EXCLUDED.source_updated_at,
                raw_payload = EXCLUDED.raw_payload
        """),
        {
            "source": source[:32],
            "ext_id": external_corp_action_id[:160],
            "secid": secid[:24].upper(),
            "ticker": ticker[:24].upper(),
            "ex_date": ex_date,
            "amount": amount_per_share,
            "currency": (currency or "")[:12] or None,
            "src_upd": source_updated_at,
            "raw": json.dumps(raw_payload, ensure_ascii=False, default=str),
        },
    )


def ingest_security_dividends_payload(db: Session, secid: str, payload: Dict[str, Any]) -> int:
    cols, data = _parse_iss_block(payload, "dividends")
    if not cols or not data:
        return 0
    idx = {c: i for i, c in enumerate(cols)}
    n = 0
    sid = secid.strip().upper()
    for row in data:
        try:
            r_sec = str(row[idx.get("secid", idx.get("SECID", 0))]).strip().upper() or sid
            isin = str(row[idx.get("isin", -1)] or "") if "isin" in idx else ""
            rdate_raw = row[idx.get("registryclosedate", 1)] if "registryclosedate" in idx else None
            if not rdate_raw:
                continue
            if isinstance(rdate_raw, date):
                ex_d = rdate_raw
            else:
                ex_d = date.fromisoformat(str(rdate_raw)[:10])
            val = row[idx["value"]] if "value" in idx else None
            cur = str(row[idx["currencyid"]]) if "currencyid" in idx and row[idx["currencyid"]] else None
            amt = Decimal(str(val)) if val is not None else None
            ext_id = f"securities_dividends:{r_sec}:{ex_d.isoformat()}:{val}"
            raw = {"row": row, "columns": cols}
            upsert_equity_dividend_row(
                db,
                source="securities_dividends",
                external_corp_action_id=ext_id[:160],
                secid=r_sec,
                ticker=r_sec,
                ex_date=ex_d,
                amount_per_share=amt,
                currency=cur,
                source_updated_at=datetime.now(timezone.utc),
                raw_payload=raw,
            )
            n += 1
        except Exception as ex:
            logger.debug("skip dividend row secid=%s err=%s", sid, ex)
    return n


def _securities_dividends_fallback_is_fresh(db: Session, *, schema: str) -> bool:
    """True если недавно уже бегали per-ticker dividends.json (источник securities_dividends)."""
    row = db.execute(
        text(f"""
            SELECT MAX(source_updated_at) AS mx
            FROM {schema}.equity_dividend_events
            WHERE source = 'securities_dividends'
        """),
    ).scalar()
    if row is None or not isinstance(row, datetime):
        return False
    mx = row if row.tzinfo else row.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - mx.astimezone(timezone.utc)
    return age.total_seconds() < settings.CORP_ACTIONS_SECURITIES_DIVIDENDS_MIN_INTERVAL_HOURS * 3600


async def sync_dividends_via_securities_endpoint(db: Session, secids: List[str]) -> int:
    """Fallback when CCI feed is unavailable (per-security dividends.json)."""
    total = 0
    for sec in secids:
        s = sec.strip().upper()
        if not s:
            continue
        try:
            payload = await fetch_security_dividends_json(s)
            total += ingest_security_dividends_payload(db, s, payload)
        except Exception as e:
            logger.warning("dividend fetch failed secid=%s: %s", s, e)
    return total


async def sync_dividends_cci_incremental(db: Session) -> Tuple[int, bool]:
    """CCI incremental sync.

    Returns (rows_upserted, cci_reachable). If cci_reachable is True, caller should
    not hammer per-ticker dividends.json — CCI ответил штатно (в т.ч. «нет новых строк»).
    """
    schema = settings.DB_SCHEMA
    row = db.execute(
        text(f"SELECT MAX(source_updated_at) FROM {schema}.equity_dividend_events WHERE source = 'cci'"),
    ).scalar()
    updated_after = row if isinstance(row, datetime) else None
    written = 0
    start = 0
    page = 0
    last_page_first_key: Optional[str] = None
    try:
        while page < CCI_MAX_PAGES:
            payload = await fetch_cci_dividends_page(updated_after=updated_after, start=start)
            cols, data = _parse_iss_block(payload, "dividends")
            if not data:
                break
            idx = {c: i for i, c in enumerate(cols)}
            page_first_key: Optional[str] = None
            for row in data:
                try:
                    ext = None
                    for key in ("id", "event_id", "corporate_action_id", "disclosure_r_id"):
                        if key in idx and row[idx[key]] is not None:
                            ext = str(row[idx[key]])
                            break
                    if not ext:
                        ext = json.dumps(row, ensure_ascii=False, default=str)[:140]
                    if page_first_key is None:
                        page_first_key = ext
                    sec_col = idx.get("secid", idx.get("SECID", 0))
                    secid = str(row[sec_col]).strip().upper()
                    tk = str(row[idx["ticker"]]).strip().upper() if "ticker" in idx else secid
                    ex_raw = None
                    for c in ("ex_date", "registryclosedate"):
                        if c in idx:
                            ex_raw = row[idx[c]]
                            break
                    if ex_raw is None:
                        continue
                    if isinstance(ex_raw, date):
                        ex_d = ex_raw
                    else:
                        ex_d = date.fromisoformat(str(ex_raw)[:10])
                    amt = None
                    cur = None
                    if "value" in idx and row[idx["value"]] is not None:
                        amt = Decimal(str(row[idx["value"]]))
                    if "currencyid" in idx and row[idx["currencyid"]]:
                        cur = str(row[idx["currencyid"]])
                    src_upd = datetime.now(timezone.utc)
                    upsert_equity_dividend_row(
                        db,
                        source="cci",
                        external_corp_action_id=("cci:" + ext)[:160],
                        secid=secid,
                        ticker=tk,
                        ex_date=ex_d,
                        amount_per_share=amt,
                        currency=cur,
                        source_updated_at=src_upd,
                        raw_payload={"columns": cols, "row": row},
                    )
                    written += 1
                except Exception as ex:
                    logger.debug("cci row skip: %s", ex)
            if page_first_key is not None and page_first_key == last_page_first_key:
                logger.warning(
                    "CCI dividends pagination stuck at start=%s (repeated first row); stopping",
                    start,
                )
                break
            last_page_first_key = page_first_key
            if len(data) < 100:
                break
            start += len(data)
            page += 1
        if page >= CCI_MAX_PAGES:
            logger.warning("CCI dividends pagination reached max pages=%s at start=%s", CCI_MAX_PAGES, start)
    except Exception as e:
        logger.info("CCI dividends unavailable or error (%s); use securities fallback", e)
        return 0, False
    return written, True


async def run_scheduled_dividend_etl(db: Session) -> Dict[str, Any]:
    schema = settings.DB_SCHEMA
    n_cci, cci_ok = await sync_dividends_cci_incremental(db)
    if n_cci > 0:
        db.commit()
        return {"source": "cci", "upserted": n_cci}
    if cci_ok:
        db.commit()
        return {"source": "cci", "upserted": 0, "detail": "no_new_cci_rows"}
    rows = db.execute(
        text(f"SELECT secid FROM {schema}.tqbr_securities ORDER BY secid LIMIT 400"),
    ).fetchall()
    secids = [str(r[0]) for r in rows if r and r[0]]
    if not secids:
        logger.warning("tqbr_securities empty; dividend ETL skipped securities fallback")
        db.commit()
        return {"source": "none", "upserted": 0}
    if _securities_dividends_fallback_is_fresh(db, schema=schema) and not settings.CORP_ACTIONS_FORCE_SECURITIES_DIVIDENDS_SYNC:
        logger.info(
            "securities dividends fallback skipped (last securities_dividends sync < %.1fh; "
            "set CORP_ACTIONS_FORCE_SECURITIES_DIVIDENDS_SYNC=1 to force)",
            settings.CORP_ACTIONS_SECURITIES_DIVIDENDS_MIN_INTERVAL_HOURS,
        )
        db.commit()
        return {"source": "securities_dividends_skipped", "upserted": 0}
    n = await sync_dividends_via_securities_endpoint(db, secids)
    db.commit()
    return {"source": "securities_dividends", "upserted": n}


TQBR_URL = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"

# Не дергать MOEX на каждый рестарт: полный sync только если таблица пуста/мала или устарела.
_TQBR_SYNC_MIN_ROWS = 120
_TQBR_SYNC_MAX_AGE_HOURS = 6.0


def _tqbr_reference_is_fresh(db: Session, *, schema: str) -> bool:
    row = db.execute(
        text(f"""
            SELECT COUNT(*)::bigint AS n, MAX(updated_at) AS mx
            FROM {schema}.tqbr_securities
        """),
    ).mappings().first()
    if not row:
        return False
    n = int(row.get("n") or 0)
    if n < _TQBR_SYNC_MIN_ROWS:
        return False
    mx = row.get("mx")
    if mx is None:
        return False
    if not isinstance(mx, datetime):
        return False
    if mx.tzinfo is None:
        mx = mx.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - mx.astimezone(timezone.utc)
    return age.total_seconds() < _TQBR_SYNC_MAX_AGE_HOURS * 3600


async def sync_tqbr_securities_reference(db: Session) -> int:
    """Один запрос к ISS: список бумаг доски TQBR → `ganaly.tqbr_securities`.

    Доска TQBR целиком умещается в один ответ; параметр `start` для этого URL
    фактически не режет выборку — старый цикл с пагинацией давал N одинаковых
    GET и лишние UPSERT.
    """
    schema = settings.DB_SCHEMA
    if _tqbr_reference_is_fresh(db, schema=schema):
        logger.info(
            "tqbr_securities: skip MOEX sync (%s+ rows, max(updated_at) < %.1fh)",
            _TQBR_SYNC_MIN_ROWS,
            _TQBR_SYNC_MAX_AGE_HOURS,
        )
        return 0
    params = {
        "iss.meta": "off",
        "iss.only": "securities",
        "securities.columns": "SECID,SHORTNAME,ISIN",
        "securities.limit": 10000,
    }
    payload = await _http_get_json(TQBR_URL, params)
    cols, data = _parse_iss_block(payload, "securities")
    if not data:
        return 0
    idx = {c.upper(): i for i, c in enumerate(cols)}
    i_id = idx.get("SECID", 0)
    i_sn = idx.get("SHORTNAME", 1) if "SHORTNAME" in idx else None
    i_isin = idx.get("ISIN", 2) if "ISIN" in idx else None
    batch: List[Tuple[str, Optional[str], Optional[str]]] = []
    for row in data:
        try:
            secid = str(row[i_id]).strip().upper()
            if not secid:
                continue
            sn = str(row[i_sn]) if i_sn is not None and i_sn < len(row) else None
            isin = str(row[i_isin]) if i_isin is not None and i_isin < len(row) else None
            batch.append((secid, sn, isin))
        except Exception as ex:
            logger.debug("tqbr row skip: %s", ex)
    if not batch:
        return 0
    return _bulk_upsert_tqbr_securities(db, schema, batch)
