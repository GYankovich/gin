"""Pydantic API schemas for robots v2."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.robots_v2.validator import ValidationIssue


class RobotV2ListRequest(BaseModel):
    robot_status: list[int] | None = Field(default=None, description="Filter by status dictionary values")
    robot_type: list[int] | None = Field(default=None, description="1=portfolio updater, 2=trading")


class RobotV2CreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int | None = Field(default=None, description="If set — update existing robot")
    name: str = Field(..., min_length=1, max_length=50)
    type: int = Field(..., description="1=portfolio updater, 2=trading")
    token_id: int = Field(..., alias="tokenId")
    config: dict[str, Any]
    status: int | None = Field(
        default=None,
        description="Optional override on create/update: 1=enabled, 2=stopped (dictionary ROBOT.STATUS). Default on create is 1.",
    )

    @field_validator("type")
    @classmethod
    def _allowed_types(cls, v: int) -> int:
        if v not in (1, 2):
            raise ValueError("type must be 1 (portfolio updater) or 2 (trading)")
        return v


class RobotV2DeleteRequest(BaseModel):
    robot_id: int = Field(..., alias="robotId", ge=1)


class RobotV2ValidateRequest(BaseModel):
    type: int = Field(..., description="1=portfolio updater, 2=trading")
    config: dict[str, Any]


class RobotV2ValidateResponse(BaseModel):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class RobotV2ChangeStatusRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    robot_id: int = Field(..., alias="robotId", ge=1)
    status: int
    stop_mode: Literal["soft", "hard"] | None = Field(default=None, alias="stopMode")


class RobotV2StartRequest(BaseModel):
    stop_mode: Literal["soft", "hard"] | None = Field(default=None, alias="stopMode")
    virtual_capital: float | None = Field(default=None, alias="virtualCapital", gt=0)


class RobotV2PreviewUniverseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token_id: int = Field(..., alias="tokenId")
    instrument_type: str = Field(default="stock", alias="instrumentType")
    universe: dict[str, Any]
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, alias="pageSize", ge=1, le=100)


class RobotV2Response(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    name: str
    type: int
    type_name: str | None = Field(default=None, alias="typeName")
    token_id: int | None = Field(alias="tokenId")
    status: int
    status_name: str | None = Field(default=None, alias="statusName")
    config_version: int = Field(alias="configVersion")
    config: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    last_started: datetime | None = Field(default=None, alias="lastStarted")
    session_state: str | None = Field(
        default=None,
        alias="sessionState",
        description="Live session state for type=2 (from session_manager); null when idle",
    )


class RobotV2ModuleResponse(BaseModel):
    enabled: bool = True


class RobotV2ListResponse(BaseModel):
    items: list[RobotV2Response]
    total: int


class RobotV2StatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    robot_id: int = Field(alias="robotId")
    status: int
    session_state: str | None = Field(default=None, alias="sessionState")
    message: str | None = None
    mode: str | None = None
    cycle_number: int | None = Field(default=None, alias="cycleNumber")
    equity: float | None = None
    cash: float | None = None
    open_positions: list[dict[str, Any]] | None = Field(default=None, alias="openPositions")
    positions_source: str | None = Field(
        default=None,
        alias="positionsSource",
        description="session | broker — where openPositions came from",
    )
    universe: list[str] | None = None
    last_cycle_at: str | None = Field(default=None, alias="lastCycleAt")
    positions_updated_at: str | None = Field(
        default=None,
        alias="positionsUpdatedAt",
        description="When position marks (current prices) were last refreshed",
    )
    ws_healthy: bool | None = Field(default=None, alias="wsHealthy")
    decisions: list[dict[str, Any]] | None = None
    equity_curve: list[dict[str, Any]] | None = Field(default=None, alias="equityCurve")
    cycle_stage: str | None = Field(default=None, alias="cycleStage")
    cycle_progress: float | None = Field(default=None, alias="cycleProgress")
    cycle_detail: str | None = Field(default=None, alias="cycleDetail")
    cycle_skip_reason: str | None = Field(default=None, alias="cycleSkipReason")
    last_triggered_by: str | None = Field(default=None, alias="lastTriggeredBy")
    last_ticker_scan: list[dict[str, Any]] | None = Field(default=None, alias="tickerScan")
    last_ticker_scan_at: str | None = Field(default=None, alias="tickerScanAt")
    open_orders: list[dict[str, Any]] | None = Field(default=None, alias="openOrders")
    bootstrap_ready: bool | None = Field(default=None, alias="bootstrapReady")
    universe_refreshed_at: str | None = Field(default=None, alias="universeRefreshedAt")


class RobotV2UniverseRefreshResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    robot_id: int = Field(alias="robotId")
    universe: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    reason: str
    kept_previous: bool = Field(default=False, alias="keptPrevious")
    refreshed_at: str | None = Field(default=None, alias="refreshedAt")
    ticker_scan: list[dict[str, Any]] | None = Field(default=None, alias="tickerScan")


class RobotV2SessionItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    robot_id: int = Field(alias="robotId")
    mode: str
    virtual_capital: float | None = Field(default=None, alias="virtualCapital")
    account_id: str | None = Field(default=None, alias="accountId")
    started_at: datetime = Field(alias="startedAt")
    ended_at: datetime | None = Field(default=None, alias="endedAt")
    stop_reason: str | None = Field(default=None, alias="stopReason")


class RobotV2SessionListResponse(BaseModel):
    items: list[RobotV2SessionItem]
    total: int


class RobotV2FillItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    order_id: str = Field(alias="orderId")
    robot_id: int = Field(alias="robotId")
    ticker: str
    side: str
    quantity: float
    price: float
    pnl: float | None = Field(default=None, description="Deprecated: use ledgerPnl")
    ledger_pnl: float | None = Field(default=None, alias="ledgerPnl")
    realized_pnl: float | None = Field(default=None, alias="realizedPnl")
    net_pnl: float | None = Field(
        default=None,
        alias="netPnl",
        description="After commission and tax on profit (SELL legs only)",
    )
    commission: float | None = None
    kind: str
    filled_at: datetime = Field(alias="filledAt")


class RobotV2FillListResponse(BaseModel):
    items: list[RobotV2FillItem]
    total: int


class RobotV2CycleItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    session_id: str = Field(alias="sessionId")
    robot_id: int = Field(alias="robotId")
    cycle_number: int = Field(alias="cycleNumber")
    triggered_by: str = Field(alias="triggeredBy")
    started_at: datetime = Field(alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    status: str
    skip_reason: str | None = Field(default=None, alias="skipReason")
    equity: float | None = None
    stats: dict[str, Any] = Field(default_factory=dict)


class RobotV2CycleListResponse(BaseModel):
    items: list[RobotV2CycleItem]
    total: int


class RobotV2DecisionItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    cycle_id: str = Field(alias="cycleId")
    robot_id: int = Field(alias="robotId")
    stage: str
    outcome: str
    code: str
    message: str | None = None
    ticker: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(alias="createdAt")


class RobotV2DecisionListResponse(BaseModel):
    items: list[RobotV2DecisionItem]
    total: int


class RobotV2SignalItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    cycle_id: str = Field(alias="cycleId")
    robot_id: int = Field(alias="robotId")
    ticker: str
    side: str
    kind: str
    reason: str | None = None
    price: float | None = None
    entry_price: float | None = Field(default=None, alias="entryPrice")
    delta_pct: float | None = Field(default=None, alias="deltaPct")
    created_at: datetime = Field(alias="createdAt")


class RobotV2SignalListResponse(BaseModel):
    items: list[RobotV2SignalItem]
    total: int


class RobotV2OrderItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    cycle_id: str = Field(alias="cycleId")
    robot_id: int = Field(alias="robotId")
    ticker: str
    side: str
    kind: str
    quantity: float
    price: float | None = None
    status: str
    mode: str
    order_type: str = Field(default="MARKET", alias="orderType")
    broker_order_id: str | None = Field(default=None, alias="brokerOrderId")
    reject_reason: str | None = Field(default=None, alias="rejectReason")
    submitted_at: datetime = Field(alias="submittedAt")


class RobotV2OrderListResponse(BaseModel):
    items: list[RobotV2OrderItem]
    total: int


class RobotV2RoundTripItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    ticker: str
    buy_at: datetime | None = Field(default=None, alias="buyAt")
    buy_price: float | None = Field(default=None, alias="buyPrice")
    buy_qty: float | None = Field(default=None, alias="buyQty")
    sell_at: datetime | None = Field(default=None, alias="sellAt")
    sell_listed_price: float | None = Field(default=None, alias="sellListedPrice")
    sell_fill_price: float | None = Field(default=None, alias="sellFillPrice")
    sell_qty: float | None = Field(default=None, alias="sellQty")
    status: str
    reason: str | None = None
    net_pnl: float | None = Field(default=None, alias="netPnl")
    realized_pnl: float | None = Field(default=None, alias="realizedPnl")


class RobotV2RoundTripListResponse(BaseModel):
    items: list[RobotV2RoundTripItem]
    total: int


AuditDataType = Literal["sessions", "fills", "cycles", "decisions", "signals", "orders", "roundTrips"]


class RobotV2AuditRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    robot_id: int = Field(..., alias="robotId", ge=1)
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    session_id: str | None = Field(default=None, alias="sessionId")
    types: list[AuditDataType] | None = Field(
        default=None,
        description="Requested audit sections; omit to return all",
    )


class RobotV2AuditSection(BaseModel):
    items: list[Any]
    total: int


class RobotV2AuditResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    robot_id: int = Field(alias="robotId")
    sessions: RobotV2AuditSection | None = None
    fills: RobotV2AuditSection | None = None
    cycles: RobotV2AuditSection | None = None
    decisions: RobotV2AuditSection | None = None
    signals: RobotV2AuditSection | None = None
    orders: RobotV2AuditSection | None = None
    round_trips: RobotV2AuditSection | None = Field(default=None, alias="roundTrips")
