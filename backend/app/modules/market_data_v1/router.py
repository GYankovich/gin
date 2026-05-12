"""REST `/api/v1/market-data/*` для ARCH-01: jobs загрузки и чтение свечей из общего кеша."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from app.modules.market_data_v1 import service
from app.modules.market_data_v1.schemas import (
    CandleLoadJobCreate,
    CandleLoadJobCreateResponse,
    CandleLoadJobStatus,
    CandlesQueryResponse,
)

router = APIRouter(prefix="/v1/market-data", tags=["market-data-v1"])


@router.post(
    "/candle-load-jobs",
    response_model=CandleLoadJobCreateResponse,
    status_code=status.HTTP_200_OK,
)
def create_candle_load_job(
        body: CandleLoadJobCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    return service.create_candle_load_job(
        db,
        user_id=int(current_user.id),
        body=body,
        idempotency_key=idempotency_key,
    )


@router.get("/candle-load-jobs/{job_id}", response_model=CandleLoadJobStatus)
def get_candle_load_job(
        job_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    return service.get_candle_load_job(db, job_id, int(current_user.id))


@router.get("/candles", response_model=CandlesQueryResponse)
def get_candles(
        tickers: List[str] = Query(..., description="Повторяющийся query-параметр, например ?tickers=SBER&tickers=GAZP"),
        board: str = Query(default="TQBR"),
        interval: str = Query(...),
        from_: datetime = Query(..., alias="from"),
        to: datetime = Query(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    _ = current_user
    return service.query_candles(
        db,
        tickers=tickers,
        board=board.strip().upper() or "TQBR",
        interval=interval,
        from_ts=from_,
        to_ts=to,
    )
