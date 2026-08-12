"""Universe Service schemas (greenfield Part III)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.robots_v2.config.v4_schema import InstrumentType, UniverseConfig


class RejectedInstrument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ticker: str
    stage: Literal["catalog", "historical", "snapshot", "cap", "excluded", "broker"]
    code: str
    message: str


class PreviewAsset(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ticker: str
    name: str = ""
    price: float = 0.0
    volume24h: float = 0.0
    atr: float = 0.0
    included: bool = True


class UniversePreview(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    as_of: datetime = Field(alias="asOf")
    total: int
    page: int = 1
    page_size: int = Field(default=20, alias="pageSize")
    assets: list[PreviewAsset]
    rejected_sample: list[RejectedInstrument] = Field(default_factory=list, alias="rejectedSample")
    job_id: str | None = Field(default=None, alias="jobId")


class InstrumentRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ticker: str
    name: str = ""
    figi: str | None = None
    symbol_id: str | None = Field(default=None, alias="symbolId")
    board: str | None = None
    lot_size: int = Field(default=1, alias="lotSize")
    min_notional: float = Field(default=0.0, alias="minNotional")
    currency: str = "RUB"
    instrument_type: InstrumentType = Field(default="stock", alias="instrumentType")


class ResolvedUniverseStats(BaseModel):
    candidate_count: int = Field(alias="candidateCount")
    after_historical: int = Field(alias="afterHistorical")
    after_snapshot: int = Field(alias="afterSnapshot")
    final_count: int = Field(alias="finalCount")


class ResolvedUniverse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    robot_id: int | None = Field(default=None, alias="robotId")
    mode: Literal["fixed", "index", "screener"]
    as_of: datetime = Field(alias="asOf")
    instruments: list[InstrumentRef]
    rejected: list[RejectedInstrument] = Field(default_factory=list)
    stats: ResolvedUniverseStats
    cache_key: str = Field(alias="cacheKey")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")


class UniversePreviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token_id: int = Field(..., alias="tokenId")
    instrument_type: InstrumentType = Field(default="stock", alias="instrumentType")
    universe: dict[str, Any]
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, alias="pageSize", ge=1, le=100)


class UniverseResolveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token_id: int = Field(..., alias="tokenId")
    instrument_type: InstrumentType = Field(default="stock", alias="instrumentType")
    universe: dict[str, Any]
    robot_id: int | None = Field(default=None, alias="robotId")


class ValidateTickersRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token_id: int = Field(..., alias="tokenId")
    instrument_type: InstrumentType = Field(default="stock", alias="instrumentType")
    tickers: list[str]


class ValidateTickersResponse(BaseModel):
    valid: list[str]
    invalid: list[RejectedInstrument]


class IndexListItem(BaseModel):
    code: str
    name: str
    constituent_count: int = Field(alias="constituentCount")
    market: Literal["moex", "crypto"]


class IndexListResponse(BaseModel):
    items: list[IndexListItem]
