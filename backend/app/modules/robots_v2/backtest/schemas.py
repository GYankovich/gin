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
    async_execution: bool = Field(default=True, alias="asyncExecution")

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
    error_message: str | None = None


class RobotV2BacktestDetailsResponse(RobotV2BacktestStatusResponse):
    total_return_percent: float | None = None
    max_drawdown_percent: float | None = None
    final_equity: float | None = None
    trades_total: int = 0
    result_payload: dict[str, Any] = Field(default_factory=dict)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    orders: list[dict[str, Any]] = Field(default_factory=list)
    portfolio_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    daily_summary: list[dict[str, Any]] = Field(default_factory=list)
