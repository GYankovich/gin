from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class MarketInstrumentRow(BaseModel):
    figi: str
    ticker: Optional[str] = None
    name: Optional[str] = None
    instrument_type: Optional[str] = None
    candle_interval: str
    first_candle_at: Optional[str] = None
    last_candle_at: Optional[str] = None
    candle_count: int = 0


class MarketInstrumentListResponse(BaseModel):
    items: List[MarketInstrumentRow] = Field(default_factory=list)


class MarketSyncRequest(BaseModel):
    figi: str = Field(..., min_length=4, max_length=32)
    candle_interval: str = "CANDLE_INTERVAL_DAY"
    years: int = Field(default=5, ge=1, le=15)
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    data_source: str = Field(default="tinvest")
    token_id: Optional[int] = None
    ticker: Optional[str] = None
    name: Optional[str] = None


class MarketSyncResponse(BaseModel):
    figi: str
    interval: str
    years: int
    rows_upserted: int


class MarketBacktestRequest(BaseModel):
    figi: str
    candle_interval: str = "CANDLE_INTERVAL_DAY"
    strategy: str = "ma_cross"
    strategy_params: Dict[str, Any] = Field(default_factory=dict)
    risk: Dict[str, Any] = Field(default_factory=dict)
    costs: Dict[str, Any] = Field(default_factory=dict)
    from_date: datetime
    to_date: datetime
    initial_capital: float = Field(default=1_000_000, ge=1000)
    token_id: Optional[int] = None
    ticker: Optional[str] = None
    data_source: str = Field(default="tinvest")
    fetch_if_missing: bool = True

    @model_validator(mode="after")
    def validate_dates(self):
        if self.to_date <= self.from_date:
            raise ValueError("to_date must be after from_date")
        return self


class MarketBacktestSaveRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    request_payload: Dict[str, Any]
    result_payload: Dict[str, Any]


class MarketBacktestSavedItem(BaseModel):
    id: int
    user_id: int
    name: Optional[str] = None
    figi: str
    candle_interval: str
    strategy: str
    from_date: str
    to_date: str
    initial_capital: float
    request_payload: Dict[str, Any] = Field(default_factory=dict)
    result_payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class MarketBacktestListResponse(BaseModel):
    items: List[MarketBacktestSavedItem] = Field(default_factory=list)


class MarketEnsureCandlesRequest(BaseModel):
    figi: str = Field(..., min_length=1, max_length=64)
    ticker: Optional[str] = None
    candle_interval: str = "CANDLE_INTERVAL_DAY"
    from_date: datetime
    to_date: datetime
    data_source: str = Field(default="moex")
    token_id: Optional[int] = None
    name: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.to_date <= self.from_date:
            raise ValueError("to_date must be after from_date")
        return self


class MarketEnsureCandlesResponse(BaseModel):
    figi: str
    ticker: Optional[str] = None
    candle_interval: str
    from_date: str
    to_date: str
    was_full_in_db: bool
    rows_loaded: int
    candle_count: int
    stages: List[str] = Field(default_factory=list)
    candles: List[Dict[str, Any]] = Field(default_factory=list)
