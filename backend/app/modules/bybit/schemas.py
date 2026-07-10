"""Pydantic schemas for ByBit read-only market API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class BybitFundingRateResponse(BaseModel):
    symbol: str
    instrument_category: Literal["spot", "linear", "inverse"]
    funding_rate: float = Field(description="Current funding rate as decimal fraction (0.0001 = 0.01%)")
    next_funding_time: Optional[datetime] = Field(
        default=None,
        description="Next funding settlement time (UTC); null for spot",
    )
    testnet: bool
    source: str = "bybit_tickers"


class BybitInstrumentItem(BaseModel):
    symbol: str
    base_coin: str = ""
    quote_coin: str = ""
    status: Optional[str] = None
    category: Literal["spot", "linear", "inverse"]


class BybitInstrumentsResponse(BaseModel):
    items: list[BybitInstrumentItem] = Field(default_factory=list)
    total: int = 0
    category: Literal["spot", "linear", "inverse"]
    testnet: bool


class BybitUniverseScreeningPreviewRequest(BaseModel):
    testnet: bool = False
    instrument_category: Literal["spot", "linear", "inverse"] = "linear"
    min_volume_24h_usd: float = Field(default=50_000_000, ge=0)
    max_spread_bps: float = Field(default=15, ge=0)
    min_funding_rate_pct: Optional[float] = None
    max_funding_rate_pct: Optional[float] = None
    min_open_interest_usd: Optional[float] = None
    min_lsr: Optional[float] = None
    max_lsr: Optional[float] = None
    min_rvol: Optional[float] = None
    min_atr_percent: Optional[float] = None
    max_atr_percent: Optional[float] = None
    lookback_days: int = Field(default=20, ge=1, le=365)


class BybitUniverseScreeningPreviewResponse(BaseModel):
    accepted: int = 0
    scanned: int = 0
    message: Optional[str] = None
    skipped: bool = False


class BybitLiveSmokePosition(BaseModel):
    figi: Optional[str] = None
    type: Optional[str] = None
    qty: Optional[float] = None
    side: Optional[str] = None


class BybitLiveSmokeResponse(BaseModel):
    ok: bool
    mainnet: bool = True
    leverage: int = 1
    symbol: str
    instrument_category: str = "linear"
    query_api: Optional[str] = None
    accounts_count: Optional[int] = None
    total_equity: Optional[float] = None
    free_funds: Optional[float] = None
    free_funds_check: Optional[float] = None
    positions_count: int = 0
    positions: list[BybitLiveSmokePosition] = Field(default_factory=list)
    candles_6h: Optional[int] = None
    message: Optional[str] = None


__all__ = [
    "BybitFundingRateResponse",
    "BybitInstrumentItem",
    "BybitInstrumentsResponse",
    "BybitUniverseScreeningPreviewRequest",
    "BybitUniverseScreeningPreviewResponse",
    "BybitLiveSmokePosition",
    "BybitLiveSmokeResponse",
]
