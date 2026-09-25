"""Pydantic schemas for OsEngine live ingest API."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class IngestCandleItem(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=32)
    board: str = Field(default="TQBR", max_length=16)
    interval: str = Field(..., min_length=1, max_length=16, description="GIN cache label: I1, M5, D1, …")
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


class IngestCandlesRequest(BaseModel):
    candles: List[IngestCandleItem] = Field(default_factory=list, max_length=5000)
    subscribed_instruments: Optional[int] = None


class IngestTickItem(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=32)
    board: str = Field(default="TQBR", max_length=16)
    time: datetime
    price: float
    quantity: float
    side: Optional[Literal["buy", "sell", "unknown"]] = None
    trade_id: Optional[str] = Field(default=None, max_length=64)


class IngestTicksRequest(BaseModel):
    ticks: List[IngestTickItem] = Field(default_factory=list, max_length=10000)
    subscribed_instruments: Optional[int] = None


class DepthLevel(BaseModel):
    price: float
    quantity: float


class IngestDepthItem(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=32)
    board: str = Field(default="TQBR", max_length=16)
    time: Optional[datetime] = None
    bids: List[DepthLevel] = Field(default_factory=list, max_length=50)
    asks: List[DepthLevel] = Field(default_factory=list, max_length=50)


class IngestDepthRequest(BaseModel):
    books: List[IngestDepthItem] = Field(default_factory=list, max_length=500)
    subscribed_instruments: Optional[int] = None


class IngestResult(BaseModel):
    accepted: int = 0
    stream: str
    market: str


class LiveStatusResponse(BaseModel):
    enabled: bool
    bridge_connected: bool
    subscribed_instruments: int = 0
    last_candle_at: Optional[str] = None
    last_tick_at: Optional[str] = None
    last_depth_at: Optional[str] = None
    lag_seconds: Optional[float] = None
    detail: str = ""
