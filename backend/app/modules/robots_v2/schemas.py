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
    token_id: int | None = Field(alias="tokenId")
    status: int
    config_version: int = Field(alias="configVersion")
    config: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


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
    universe: list[str] | None = None
    last_cycle_at: str | None = Field(default=None, alias="lastCycleAt")
    ws_healthy: bool | None = Field(default=None, alias="wsHealthy")
    decisions: list[dict[str, Any]] | None = None
    equity_curve: list[dict[str, Any]] | None = Field(default=None, alias="equityCurve")
