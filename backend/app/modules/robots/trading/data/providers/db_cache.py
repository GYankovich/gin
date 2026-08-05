"""Чтение свечей из candles_cache (DB-first, без HTTP)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

_DEFAULT_BULK_BATCH_SIZE = 200


def _normalize_instrument_ids(instrument_ids: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in instrument_ids:
        iid = str(raw or "").strip().upper()
        if not iid or iid in seen:
            continue
        seen.add(iid)
        out.append(iid)
    return out


def _group_rows_by_instrument(rows: Sequence[Any]) -> Dict[str, List[Any]]:
    grouped: Dict[str, List[Any]] = {}
    for row in rows:
        iid = str(row.get("instrument_id") or "").strip().upper()
        if not iid:
            continue
        grouped.setdefault(iid, []).append(row)
    return grouped


def _fetch_candles_cache_bulk_exact(
    db: Session,
    *,
    market: str,
    instrument_ids: Sequence[str],
    interval_code: str,
    from_dt: datetime,
    to_dt_exclusive: datetime,
) -> List[Any]:
    if not instrument_ids:
        return []
    return list(
        db.execute(
            text(f"""
                SELECT instrument_id, candle_time, open, high, low, close, volume
                FROM candles_cache
                WHERE market = :market
                  AND instrument_id = ANY(:instrument_ids)
                  AND interval = :interval
                  AND candle_time >= :from_date
                  AND candle_time < :to_date
                ORDER BY instrument_id ASC, candle_time ASC
            """),
            {
                "market": market,
                "instrument_ids": list(instrument_ids),
                "interval": interval_code,
                "from_date": from_dt,
                "to_date": to_dt_exclusive,
            },
        ).mappings().all()
    )


def _fetch_candles_cache_bulk_alias(
    db: Session,
    *,
    market: str,
    instrument_ids: Sequence[str],
    interval_code: str,
    interval_code_num: int,
    from_dt: datetime,
    to_dt_exclusive: datetime,
) -> List[Any]:
    if not instrument_ids:
        return []

    if interval_code_num in (1, 10, 60):
        return list(
            db.execute(
                text(f"""
                    SELECT instrument_id, candle_time, open, high, low, close, volume
                    FROM candles_cache
                    WHERE market = :market
                      AND instrument_id = ANY(:instrument_ids)
                      AND interval IN (:interval_alias, :interval_i, :interval_plain, :interval_min)
                      AND candle_time >= :from_date
                      AND candle_time < :to_date
                    ORDER BY instrument_id ASC, candle_time ASC
                """),
                {
                    "market": market,
                    "instrument_ids": list(instrument_ids),
                    "interval_alias": interval_code,
                    "interval_i": f"I{interval_code_num}",
                    "interval_plain": f"{interval_code_num}m",
                    "interval_min": f"{interval_code_num}MIN",
                    "from_date": from_dt,
                    "to_date": to_dt_exclusive,
                },
            ).mappings().all()
        )
    if interval_code_num == 5:
        return list(
            db.execute(
                text(f"""
                    SELECT instrument_id, candle_time, open, high, low, close, volume
                    FROM candles_cache
                    WHERE market = :market
                      AND instrument_id = ANY(:instrument_ids)
                      AND interval IN ('M5', 'I5', '5m', '5MIN')
                      AND candle_time >= :from_date
                      AND candle_time < :to_date
                    ORDER BY instrument_id ASC, candle_time ASC
                """),
                {
                    "market": market,
                    "instrument_ids": list(instrument_ids),
                    "from_date": from_dt,
                    "to_date": to_dt_exclusive,
                },
            ).mappings().all()
        )
    if interval_code == "D1":
        return list(
            db.execute(
                text(f"""
                    SELECT instrument_id, candle_time, open, high, low, close, volume
                    FROM candles_cache
                    WHERE market = :market
                      AND instrument_id = ANY(:instrument_ids)
                      AND interval IN ('D1', 'I24', '1d', '1D', 'CANDLE_INTERVAL_DAY')
                      AND candle_time >= :from_date
                      AND candle_time < :to_date
                    ORDER BY instrument_id ASC, candle_time ASC
                """),
                {
                    "market": market,
                    "instrument_ids": list(instrument_ids),
                    "from_date": from_dt,
                    "to_date": to_dt_exclusive,
                },
            ).mappings().all()
        )
    return []


def _needs_interval_alias_fallback(interval_code: str, interval_code_num: int) -> bool:
    return (
        interval_code_num in (1, 10, 60)
        or interval_code_num == 5
        or interval_code == "D1"
    )


def query_candles_cache_rows_bulk(
    db: Session,
    *,
    market: str = "moex",
    instrument_ids: Iterable[str],
    interval_code: str,
    interval_code_num: int,
    from_dt: datetime,
    to_dt_exclusive: datetime,
    batch_size: int = _DEFAULT_BULK_BATCH_SIZE,
) -> Dict[str, List[Any]]:
    """
    Свечи для нескольких instrument_id за 1–2 запроса на батч (вместо N отдельных SELECT).

    Семантика совпадает с повторными вызовами query_candles_cache_rows по каждому тикеру.
    """
    ids = _normalize_instrument_ids(instrument_ids)
    if not ids:
        return {}

    mkt = str(market or "moex").strip().lower()
    out: Dict[str, List[Any]] = {iid: [] for iid in ids}
    chunk = max(1, int(batch_size))

    for batch_start in range(0, len(ids), chunk):
        batch = ids[batch_start : batch_start + chunk]
        exact_rows = _fetch_candles_cache_bulk_exact(
            db,
            market=mkt,
            instrument_ids=batch,
            interval_code=interval_code,
            from_dt=from_dt,
            to_dt_exclusive=to_dt_exclusive,
        )
        for iid, rows in _group_rows_by_instrument(exact_rows).items():
            if rows:
                out[iid] = list(rows)

        if not _needs_interval_alias_fallback(interval_code, interval_code_num):
            continue

        missing = [iid for iid in batch if not out.get(iid)]
        if not missing:
            continue

        alias_rows = _fetch_candles_cache_bulk_alias(
            db,
            market=mkt,
            instrument_ids=missing,
            interval_code=interval_code,
            interval_code_num=interval_code_num,
            from_dt=from_dt,
            to_dt_exclusive=to_dt_exclusive,
        )
        for iid, rows in _group_rows_by_instrument(alias_rows).items():
            if rows:
                out[iid] = list(rows)

    return out


def query_candles_cache_rows(
    db: Session,
    *,
    market: str = "moex",
    instrument_id: str | None = None,
    ticker: str,
    interval_code: str,
    interval_code_num: int,
    from_dt: datetime,
    to_dt_exclusive: datetime,
) -> List[Any]:
    """Строки candles_cache за диапазон; учитывает legacy-алиасы interval (M5, I5, …)."""
    iid = str(instrument_id or ticker or "").strip().upper()
    if not iid:
        return []
    grouped = query_candles_cache_rows_bulk(
        db,
        market=market,
        instrument_ids=[iid],
        interval_code=interval_code,
        interval_code_num=interval_code_num,
        from_dt=from_dt,
        to_dt_exclusive=to_dt_exclusive,
        batch_size=1,
    )
    return list(grouped.get(iid) or [])


__all__ = ["query_candles_cache_rows", "query_candles_cache_rows_bulk"]
