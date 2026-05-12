#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesDmsSchemas [1]
#/// Исходный модуль `backend/app/modules/dms/schemas.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DmsSubscribeRequest(BaseModel):
    robot_id: int
    board: str = "TQBR"
    include_candles: bool = False
    candle_interval: Optional[str] = None
    candle_depth: int = 14
    snapshot_hour: Optional[int] = None
    ttl_minutes: int = 5


class DmsSubscriptionItem(BaseModel):
    id: int
    robot_id: int
    subscription_key: str
    board: str
    status: str
    requested_at: datetime
    snapshot_hour: Optional[int] = None
    snapshot_id: Optional[int] = None


class DmsSubscribeResponse(BaseModel):
    subscription: DmsSubscriptionItem
    reused_snapshot: bool = False


class MarketSnapshotItem(BaseModel):
    id: int
    snapshot_time: datetime
    board: str
    status: str
    error_message: Optional[str] = None
    ttl_minutes: int
    created_at: datetime
    securities_count: int = 0


class DmsCreateSnapshotRequest(BaseModel):
    board: str = "TQBR"
    ttl_minutes: int = 5
    is_manual: bool = True


class DmsCreateSnapshotResponse(BaseModel):
    snapshot_id: int
    status: str
    securities_count: int = 0
    message: Optional[str] = None


class DmsProcessQueueResponse(BaseModel):
    processed_subscriptions: int = 0
    created_snapshots: int = 0
    analyzer_written_rows: int = 0
    errors: List[str] = Field(default_factory=list)


class DmsCleanupResponse(BaseModel):
    moved_snapshots: int = 0
    moved_rows: int = 0
    deleted_snapshots: int = 0


class DmsPipelinePreviewRequest(BaseModel):
    robot_id: int
    board: str = "TQBR"
    filters: List[Dict[str, Any]] = Field(default_factory=list)
    mode: str = "ALL"


class DmsPipelinePreviewResponse(BaseModel):
    total_checked: int = 0
    passed: int = 0
    rejected: int = 0
    sample: List[Dict[str, Any]] = Field(default_factory=list)


class DmsInitializeDayRequest(BaseModel):
    robot_id: int
    board: str = "TQBR"
    force_refresh_snapshot: bool = False


class DmsInitializeDayResponse(BaseModel):
    robot_id: int
    board: str
    trade_date: date
    snapshot_id: int
    initialized: bool = False
    analyzer_written_rows: int = 0
    message: Optional[str] = None


class DailyUniverseItem(BaseModel):
    id: int
    robot_id: int
    trade_date: date
    ticker: str
    source: str
    filter_result: Optional[str] = None
    reject_reason: Optional[str] = None
    snapshot_id: Optional[int] = None
    price_at_filter: Optional[float] = None
    volume_at_filter: Optional[int] = None
    atr_value: Optional[float] = None
    gap_percent: Optional[float] = None
    applied_filters: Optional[Dict[str, Any]] = None
    created_at: datetime


class DailyUniverseResponse(BaseModel):
    total: int
    items: List[DailyUniverseItem] = Field(default_factory=list)


class DmsFilterLogResponse(BaseModel):
    total_checked: int = 0
    passed: int = 0
    rejected: int = 0
    items: List[DailyUniverseItem] = Field(default_factory=list)
