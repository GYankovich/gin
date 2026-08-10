"""Бизнес-логика v1: очереди загрузки свечей и чтение из shared_market_candles [ref: ARCH-01]."""

from __future__ import annotations



from collections import defaultdict

from datetime import datetime, timezone

from decimal import Decimal

from typing import Any, Dict, List, Optional, Tuple

from uuid import UUID



from fastapi import HTTPException, status

from sqlalchemy import text

from sqlalchemy.orm import Session



from app.modules.market_data_v1 import repository

from app.modules.market_data_v1.schemas import (

    CandleGap,

    CandleLoadJobCreate,

    CandleLoadJobCreateResponse,

    CandleLoadJobStatus,

    CandlesQueryResponse,

    TqbrSearchResponse,

    TqbrSecurityRow,

    candle_row_from_db,

)

from app.modules.market_data_v1.intervals import SUPPORTED_CANONICAL, moex_interval_code





def _utc(dt: datetime) -> datetime:

    if dt.tzinfo is None:

        return dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)





def _normalize_interval(interval: str) -> str:

    raw = (interval or "").strip()

    if not raw:

        raise ValueError("interval is required")

    key = raw

    if key not in SUPPORTED_CANONICAL:

        key = raw.lower()

        if key == "1m":

            return "1m"

        if key in ("60m", "1hour"):

            return "1h"

        if key in ("d1", "1day"):

            return "1d"

    if key not in SUPPORTED_CANONICAL:

        raise ValueError(f"unsupported interval: {interval}")

    return key





def _validate_window(from_ts: datetime, to_ts: datetime) -> Tuple[datetime, datetime]:

    a = _utc(from_ts)

    b = _utc(to_ts)

    if a >= b:

        raise ValueError("from must be strictly before to")

    return a, b





def create_candle_load_job(

        db: Session,

        *,

        user_id: int,

        body: CandleLoadJobCreate,

        idempotency_key: Optional[str],

) -> CandleLoadJobCreateResponse:

    try:

        interval = _normalize_interval(body.interval)

        moex_interval_code(interval)

    except ValueError as e:

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e



    try:

        from_ts, to_ts = _validate_window(body.from_, body.to)

    except ValueError as e:

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e



    try:

        job_id = repository.insert_job(

            db,

            user_id=user_id,

            board=body.board,

            interval=interval,

            from_ts=from_ts,

            to_ts=to_ts,

            tickers=body.tickers,

            idempotency_key=((idempotency_key or "").strip() or None),

        )

        db.commit()

    except Exception as e:

        db.rollback()

        raise HTTPException(

            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail=f"failed to create job: {e}",

        ) from e



    row = repository.get_job(db, job_id, user_id)

    st = str(row["status"]) if row else "queued"

    return CandleLoadJobCreateResponse(job_id=job_id, status=st)





def _float_pct(v: Any) -> float:

    if v is None:

        return 0.0

    if isinstance(v, Decimal):

        return float(v)

    return float(v)





def get_candle_load_job(db: Session, job_id: UUID, user_id: int) -> CandleLoadJobStatus:

    row = repository.get_job(db, job_id, user_id)

    if not row:

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    return CandleLoadJobStatus(

        job_id=row["id"],

        status=str(row["status"]),

        progress_percent=_float_pct(row.get("progress_percent")),

        tickers_total=int(row["tickers_total"]),

        tickers_done=int(row["tickers_done"]),

        bars_written=int(row["bars_written"]),

        message=row.get("message"),

        started_at=row.get("started_at"),

        updated_at=row.get("updated_at"),

        eta_seconds=int(row["eta_seconds"]) if row.get("eta_seconds") is not None else None,

        error=row.get("error"),

    )





def _edge_gaps(

        tickers: List[str],

        rows: List[Dict[str, Any]],

        from_ts: datetime,

        to_ts: datetime,

) -> List[CandleGap]:

    by_t: Dict[str, List[datetime]] = defaultdict(list)

    for r in rows:

        by_t[str(r["ticker"])].append(r["bucket_start"])

    gaps: List[CandleGap] = []

    for t in tickers:

        ts_list = sorted(by_t.get(t, []))

        if not ts_list:

            gaps.append(CandleGap(ticker=t, from_=from_ts, to=to_ts))

            continue

        if ts_list[0] > from_ts:

            gaps.append(CandleGap(ticker=t, from_=from_ts, to=ts_list[0]))

        if ts_list[-1] < to_ts:

            gaps.append(CandleGap(ticker=t, from_=ts_list[-1], to=to_ts))

    return gaps





def query_candles(

        db: Session,

        *,

        tickers: List[str],

        board: str,

        interval: str,

        from_ts: datetime,

        to_ts: datetime,

) -> CandlesQueryResponse:

    try:

        interval_n = _normalize_interval(interval)

        moex_interval_code(interval_n)

    except ValueError as e:

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e



    tickers_u = [t.strip().upper() for t in tickers if t and str(t).strip()]

    if not tickers_u:

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tickers required")



    a, b = _validate_window(from_ts, to_ts)

    rows = repository.list_candles(

        db,

        tickers=tickers_u,

        board=board,

        interval=interval_n,

        from_ts=a,

        to_ts=b,

    )

    candles = [candle_row_from_db(r) for r in rows]

    gaps = _edge_gaps(tickers_u, rows, a, b)

    return CandlesQueryResponse(candles=candles, gaps=gaps)


def list_tqbr_bulk(db: Session, *, limit: int = 12_000) -> TqbrSearchResponse:
    from app.modules.robots.moex_securities_updater import queries as moex_q

    sql, params = moex_q.build_list_securities_bulk_query(board="TQBR", limit=limit, active_only=True)
    rows = db.execute(text(sql), params).fetchall()
    items = [
        TqbrSecurityRow(
            secid=str(r[0]),
            shortname=str(r[1]) if r[1] is not None else None,
            isin=str(r[2]) if r[2] is not None else None,
        )
        for r in rows
        if r and r[0]
    ]
    return TqbrSearchResponse(items=items)


def search_tqbr(db: Session, *, prefix: str, limit: int = 50) -> TqbrSearchResponse:
    from app.modules.robots.moex_securities_updater import queries as moex_q

    sql, params = moex_q.build_search_securities_query(
        prefix=prefix,
        board="TQBR",
        limit=limit,
        active_only=True,
    )
    rows = db.execute(text(sql), params).fetchall()
    items = [
        TqbrSecurityRow(
            secid=str(r[0]),
            shortname=str(r[1]) if r[1] is not None else None,
            isin=str(r[2]) if r[2] is not None else None,
        )
        for r in rows
        if r and r[0]
    ]
    return TqbrSearchResponse(items=items)
