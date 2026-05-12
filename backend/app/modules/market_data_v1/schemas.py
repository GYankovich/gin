"""Pydantic-схемы REST v1 для ARCH-01 (MOEX, ticker, jobs)."""

from __future__ import annotations



from datetime import datetime

from decimal import Decimal

from typing import List, Optional

from uuid import UUID



from pydantic import BaseModel, ConfigDict, Field, field_validator





class CandleLoadJobCreate(BaseModel):

    tickers: List[str] = Field(..., min_length=1)

    board: str = Field(default="TQBR", max_length=16)

    interval: str = Field(..., max_length=32)

    from_: datetime = Field(..., serialization_alias="from", alias="from")

    to: datetime = Field(...)



    model_config = ConfigDict(populate_by_name=True)



    @field_validator("tickers")

    @classmethod

    def tickers_non_empty(cls, v: List[str]) -> List[str]:

        cleaned = [t.strip().upper() for t in v if t and str(t).strip()]

        if not cleaned:

            raise ValueError("tickers must contain at least one non-empty ticker")

        return cleaned



    @field_validator("board")

    @classmethod

    def board_upper(cls, v: str) -> str:

        return (v or "TQBR").strip().upper() or "TQBR"





class CandleLoadJobCreateResponse(BaseModel):

    job_id: UUID

    status: str





class CandleLoadJobStatus(BaseModel):

    job_id: UUID

    status: str

    progress_percent: float

    tickers_total: int

    tickers_done: int

    bars_written: int

    message: Optional[str] = None

    started_at: Optional[datetime] = None

    updated_at: Optional[datetime] = None

    eta_seconds: Optional[int] = None

    error: Optional[str] = None



    model_config = ConfigDict(from_attributes=True)





class CandleRow(BaseModel):

    ticker: str

    board: str

    interval: str

    bucket_start: datetime

    open: float

    high: float

    low: float

    close: float

    volume: Optional[int] = None

    source: Optional[str] = None





class CandleGap(BaseModel):

    ticker: str

    from_: datetime = Field(..., serialization_alias="from", alias="from")

    to: datetime



    model_config = ConfigDict(populate_by_name=True)





class CandlesQueryResponse(BaseModel):

    candles: List[CandleRow]

    gaps: List[CandleGap]





def _decimal_to_float(d: object) -> float:

    if d is None:

        return 0.0

    if isinstance(d, Decimal):

        return float(d)

    return float(d)





def candle_row_from_db(row: dict) -> CandleRow:

    return CandleRow(

        ticker=str(row["ticker"]),

        board=str(row["board"]),

        interval=str(row["interval"]),

        bucket_start=row["bucket_start"],

        open=_decimal_to_float(row.get("open")),

        high=_decimal_to_float(row.get("high")),

        low=_decimal_to_float(row.get("low")),

        close=_decimal_to_float(row.get("close")),

        volume=int(row["volume"]) if row.get("volume") is not None else None,

        source=str(row["source"]) if row.get("source") is not None else None,

    )
