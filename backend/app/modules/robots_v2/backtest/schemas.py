"""API schemas for robots v2 backtest."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RobotV2BacktestRequest(BaseModel):
    """Start a v2 backtest on historical bars."""

    model_config = ConfigDict(populate_by_name=True)

    config: dict[str, Any] = Field(..., description="TradingRobotConfigV4 JSON")
    from_date: datetime = Field(..., description="Period start (UTC)")
    to_date: datetime = Field(..., description="Period end (UTC)")
    initial_capital: float | None = Field(default=None, ge=10)
    robot_id: int | None = Field(default=None, alias="robotId")
    token_id: int | None = Field(default=None, alias="tokenId")
    async_execution: bool = Field(
        default=True,
        alias="asyncExecution",
        description="Deprecated: v2 always enqueues to heavy lane (ARCH-05). Ignored.",
    )

    @model_validator(mode="after")
    def _normalize_dates(self) -> RobotV2BacktestRequest:
        from datetime import timezone

        for attr in ("from_date", "to_date"):
            dt = getattr(self, attr)
            if dt.tzinfo is None:
                setattr(self, attr, dt.replace(tzinfo=timezone.utc))
            else:
                setattr(self, attr, dt.astimezone(timezone.utc))
        if self.to_date <= self.from_date:
            raise ValueError("to_date must be after from_date")
        return self


class RobotV2BacktestAsyncAccepted(BaseModel):
    run_id: int
    status: str = "queued"
    message: str = "Poll GET /api/v2/robots/backtest/runs/{run_id}/status"


class RobotV2BacktestTrade(BaseModel):
    id: int = 0
    figi: str
    side: str
    bar_time: str | None = None
    price: float
    quantity: int
    commission: float = 0.0
    pnl_net: float | None = None
    reason: str | None = None
    kind: str | None = None
    cycle_id: str | None = None
    signal_time: str | None = None


class RobotV2BacktestObservabilityExecutionModel(BaseModel):
    code: str = "NEXT_BAR_OPEN"
    label: str = "Fills at next bar open"
    look_ahead: bool = False


class RobotV2BacktestRejectReasonCount(BaseModel):
    code: str
    count: int


class RobotV2BacktestObservability(BaseModel):
    execution_model: RobotV2BacktestObservabilityExecutionModel = Field(
        default_factory=RobotV2BacktestObservabilityExecutionModel,
    )
    signals_logged: int = 0
    signals_truncated: bool = False
    signal_log_cap: int = 25_000
    reject_reason_counts: list[RobotV2BacktestRejectReasonCount] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)


class RobotV2BacktestFeeSummary(BaseModel):
    commission_total: float = 0.0
    funding_total: float = 0.0
    funding_events: int = 0
    tax_total: float | None = None


class RobotV2BacktestResultPayload(BaseModel):
    initial_capital: float
    final_equity: float
    total_return_percent: float
    max_drawdown_percent: float | None = None
    trades: list[RobotV2BacktestTrade] = Field(default_factory=list)
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    history_stats: dict[str, int] = Field(default_factory=dict)
    daily_summary: list[dict[str, Any]] = Field(default_factory=list)
    observability: RobotV2BacktestObservability | None = None
    fee_summary: RobotV2BacktestFeeSummary | None = None
    engine_version: str = "v2"


class RobotV2BacktestStatusResponse(BaseModel):
    run_id: int
    robot_id: int | None = None
    status: str
    requested_from: datetime
    requested_to: datetime
    started_at: datetime
    finished_at: datetime | None = None
    initial_capital: float = 0.0
    progress_percent: float | None = None
    run_phase: str | None = None
    phase_label: str | None = None
    phase_units_done: int | None = None
    phase_units_total: int | None = None
    cancel_requested: bool | None = None
    partial_result: bool | None = None
    error_message: str | None = None


class RobotV2BacktestNarrativeStep(BaseModel):
    section: str
    step: int
    text: str
    ts: str | None = None


class RobotV2BacktestDetailsResponse(RobotV2BacktestStatusResponse):
    total_return_percent: float | None = None
    max_drawdown_percent: float | None = None
    final_equity: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    win_rate_percent: float | None = None
    trades_total: int = 0
    result_payload: dict[str, Any] = Field(default_factory=dict)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    orders: list[dict[str, Any]] = Field(default_factory=list)
    portfolio_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    daily_summary: list[dict[str, Any]] = Field(default_factory=list)
    observability: RobotV2BacktestObservability | None = None
    fee_summary: RobotV2BacktestFeeSummary | None = None
    narrative: list[RobotV2BacktestNarrativeStep] = Field(default_factory=list)
    execution_events: list[dict[str, Any]] = Field(default_factory=list)
    signals_total: int = 0
    signals_truncated_inline: bool = False


class RobotV2BacktestSignalsPageResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    truncated_run: bool = False
    limit: int = 200
    offset: int = 0


class RobotV2BacktestCycleBundleResponse(BaseModel):
    cycle_id: str
    signals: list[dict[str, Any]] = Field(default_factory=list)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    orders: list[dict[str, Any]] = Field(default_factory=list)
    execution_events: list[dict[str, Any]] = Field(default_factory=list)
    config_risk_excerpt: dict[str, Any] = Field(default_factory=dict)


class RobotV2BacktestExecutionEventsResponse(BaseModel):
    run_id: int
    items: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class RobotV2BacktestNarrativeResponse(BaseModel):
    run_id: int
    items: list[RobotV2BacktestNarrativeStep] = Field(default_factory=list)
    total: int = 0


class RobotV2BacktestPriceWindowResponse(BaseModel):
    run_id: int
    ticker: str
    around: str | None = None
    bars: int = 0
    interval: str | None = None
    market: str | None = None
    candles: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "cache"
    gap: str | None = None


class RobotV2BacktestUniverseMembershipItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trade_date: date
    ticker: str
    source: str | None = None
    filter_result: str | None = None
    reject_reason: str | None = None


class RobotV2BacktestUniverseResponse(BaseModel):
    run_id: int
    items: list[RobotV2BacktestUniverseMembershipItem] = Field(default_factory=list)
    days: list[date] = Field(default_factory=list)
    total: int = 0


class RobotV2BacktestListItem(BaseModel):
    run_id: int
    robot_id: int | None = None
    bound: bool = False
    config_label: str | None = None
    display_name: str | None = None
    status: str
    requested_from: datetime
    requested_to: datetime
    started_at: datetime
    finished_at: datetime | None = None
    initial_capital: float = 0.0
    total_return_percent: float | None = None
    max_drawdown_percent: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    win_rate_percent: float | None = None
    final_equity: float | None = None
    trades_total: int = 0
    error_message: str | None = None


class RobotV2BacktestListResponse(BaseModel):
    items: list[RobotV2BacktestListItem] = Field(default_factory=list)
    total: int = 0


class RobotV2BacktestCompareRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    base_run_id: int = Field(..., alias="baseRunId")
    compare_run_id: int = Field(..., alias="compareRunId")


class RobotV2BacktestCompareResponse(BaseModel):
    base_run_id: int
    compare_run_id: int
    metrics_base: dict[str, Any] = Field(default_factory=dict)
    metrics_compare: dict[str, Any] = Field(default_factory=dict)
    metrics_diff: dict[str, Any] = Field(default_factory=dict)
    config_diff: dict[str, Any] = Field(default_factory=dict)
    base: dict[str, Any] = Field(default_factory=dict)
    compare: dict[str, Any] = Field(default_factory=dict)


class RobotV2BacktestSaveAsRobotRequest(BaseModel):
    """SPEC-05 §6.5 — create trading robot from a successful backtest run."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=50)
    token_id: int | None = Field(default=None, alias="tokenId", ge=1)
    attach_run: bool = Field(default=True, alias="attachRun")


class RobotV2BacktestSaveAsRobotResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    robot_id: int = Field(..., alias="robotId")
    run_id: int = Field(..., alias="runId")
