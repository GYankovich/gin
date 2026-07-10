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
    CandleCoverageSummaryResponse,
    TqbrSearchResponse,
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


@router.get("/candles/coverage-summary", response_model=CandleCoverageSummaryResponse)
def get_candles_coverage_summary(
        tickers: List[str] = Query(..., description="Тикеры TQBR"),
        board: str = Query(default="TQBR"),
        interval: str = Query(...),
        from_: datetime = Query(..., alias="from"),
        to: datetime = Query(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    _ = current_user
    return service.coverage_summary(
        db,
        tickers=tickers,
        board=board.strip().upper() or "TQBR",
        interval=interval,
        from_ts=from_,
        to_ts=to,
    )


@router.get("/tqbr-securities/bulk", response_model=TqbrSearchResponse)
def list_tqbr_securities_bulk(
        limit: int = Query(
            default=12_000,
            ge=1,
            le=20_000,
            description="Максимум строк из tqbr_securities (полный список для UI)",
        ),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    _ = current_user
    return service.list_tqbr_bulk(db, limit=limit)


@router.get("/tqbr-securities", response_model=TqbrSearchResponse)
def search_tqbr_securities(
        q: str = Query(..., min_length=1, description="Префикс SECID"),
        limit: int = Query(default=50, ge=1, le=200),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    _ = current_user
    return service.search_tqbr(db, prefix=q, limit=limit)
