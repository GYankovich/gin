"""Request/response schemas for /api/compute/v1 (ARCH-05 Phase C)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ComputeRunCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    config: dict[str, Any] = Field(..., description="TradingRobotConfigV4 JSON")
    from_date: datetime
    to_date: datetime
    initial_capital: float | None = Field(default=None, ge=10)
    robot_id: int | None = Field(default=None, alias="robotId")
    token_id: int | None = Field(default=None, alias="tokenId")
    priority: Literal["interactive", "batch"] = "interactive"
    labels: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize_dates(self) -> ComputeRunCreateRequest:
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


class ComputeRunAccepted(BaseModel):
    run_id: int
    status: str = "queued"
    job_id: str | None = None
    message: str = "Poll GET /api/compute/v1/runs/{run_id}"


class ComputeCancelResponse(BaseModel):
    ok: bool = True
    status: str = "cancel_requested"
    run_id: int | None = None
    batch_id: int | None = None


class ComputeCompareRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    base_run_id: int = Field(..., alias="baseRunId")
    compare_run_id: int = Field(..., alias="compareRunId")


class ComputeBatchVariant(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    variant_key: str = Field(..., alias="variantKey")
    config: dict[str, Any]


class ComputeBatchCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    robot_id: int = Field(..., alias="robotId")
    base_config: dict[str, Any] | None = Field(default=None, alias="baseConfig")
    variants: list[ComputeBatchVariant] = Field(..., min_length=1)
    from_date: datetime
    to_date: datetime
    initial_capital: float | None = Field(default=None, ge=10)
    token_id: int | None = Field(default=None, alias="tokenId")
    priority: Literal["interactive", "batch"] = "batch"
    goal: str = "balanced"

    @model_validator(mode="after")
    def _normalize_dates(self) -> ComputeBatchCreateRequest:
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


class ComputeBatchAccepted(BaseModel):
    batch_id: int
    status: str = "queued"
    items_total: int
    run_ids: list[int] = Field(default_factory=list)
    message: str = "Poll GET /api/compute/v1/batches/{batch_id}"


class ComputeBatchStatusResponse(BaseModel):
    batch_id: int
    status: str
    items_total: int = 0
    items_done: int = 0
    items_failed: int = 0
    items_cancelled: int = 0
    progress_percent: float = 0.0
    robot_id: int | None = None
    run_ids: list[int] = Field(default_factory=list)


class ComputeQueueMetrics(BaseModel):
    lane: str = "heavy"
    queued: int = 0
    running: int = 0
    as_of: datetime
