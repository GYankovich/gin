"""Greenfield trading robot config schema (v4)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIG_VERSION_V4 = 4

Goal = Literal["conservative", "moderate", "aggressive"]
InstrumentType = Literal["stock", "futures", "perpetual", "coin_futures"]
TradingMode = Literal["paper", "live"]
PollInterval = Literal["1m", "5m", "15m", "1h"]
StrategyArchetype = Literal["scalper", "momentum", "reversion", "grid"]
UniverseMode = Literal["fixed", "index", "screener"]
StopMode = Literal["soft", "hard"]
FilterMode = Literal["all", "any"]
RefreshPolicy = Literal["on_session", "daily", "on_poll"]
ScreenerPreset = Literal["high_liquidity", "volatile", "low_price", "custom"]
ReversionIndicator = Literal["rsi", "stochastic", "divergence"]


class ScheduleConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    weekdays: list[bool] = Field(..., min_length=7, max_length=7)
    time_from: str = Field(..., alias="timeFrom", pattern=r"^\d{2}:\d{2}$")
    time_to: str = Field(..., alias="timeTo", pattern=r"^\d{2}:\d{2}$")
    poll_interval: PollInterval = Field(default="5m", alias="pollInterval")

    @field_validator("weekdays")
    @classmethod
    def _at_least_one_weekday(cls, v: list[bool]) -> list[bool]:
        if not any(v):
            raise ValueError("At least one weekday must be enabled")
        return v

    @model_validator(mode="after")
    def _time_window(self) -> ScheduleConfig:
        if self.time_from >= self.time_to:
            raise ValueError("timeFrom must be earlier than timeTo")
        return self


class CoreConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    goal: Goal = "moderate"
    instrument_type: InstrumentType = Field(default="stock", alias="instrumentType")
    mode: TradingMode = "paper"
    schedule: ScheduleConfig
    advanced_mode: bool = Field(default=False, alias="advancedMode")


class ScalperParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    delta_threshold_pct: float = Field(..., alias="deltaThresholdPct", ge=1, le=20)
    requires_web_socket: Literal[True] = Field(default=True, alias="requiresWebSocket")
    min_volume_window: int = Field(default=30, alias="minVolumeWindow", ge=5, le=300)
    cooldown_sec: int = Field(default=60, alias="cooldownSec", ge=0, le=3600)


class MomentumParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ma_period: int = Field(..., alias="maPeriod", ge=20, le=200)
    volume_multiplier: float = Field(..., alias="volumeMultiplier", ge=1.5, le=5.0)
    breakout_lookback: int = Field(default=20, alias="breakoutLookback", ge=5, le=200)


class ReversionParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    indicator: ReversionIndicator
    overbought_threshold: float = Field(..., alias="overboughtThreshold", ge=70, le=90)
    oversold_threshold: float | None = Field(default=None, alias="oversoldThreshold", ge=10, le=30)
    rsi_period: int = Field(default=14, alias="rsiPeriod", ge=5, le=50)

    @model_validator(mode="after")
    def _default_oversold(self) -> ReversionParams:
        if self.oversold_threshold is None:
            object.__setattr__(self, "oversold_threshold", max(10.0, min(30.0, 100.0 - self.overbought_threshold)))
        return self


class GridParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    grid_step_atr_pct: float = Field(..., alias="gridStepAtrPct", ge=0.5, le=5)
    grid_depth: int = Field(..., alias="gridDepth", ge=3, le=20)
    base_allocation_pct: float = Field(default=30.0, alias="baseAllocationPct", ge=5, le=100)
    scale_multiplier: float = Field(default=1.2, alias="scaleMultiplier", ge=1.0, le=3.0)


class StrategyConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    archetype: StrategyArchetype
    timeframe: str
    params: dict[str, Any]

    @model_validator(mode="after")
    def _validate_params(self) -> StrategyConfig:
        if self.archetype == "scalper":
            ScalperParams.model_validate(self.params)
        elif self.archetype == "momentum":
            MomentumParams.model_validate(self.params)
        elif self.archetype == "reversion":
            ReversionParams.model_validate(self.params)
        elif self.archetype == "grid":
            GridParams.model_validate(self.params)
        return self


class ScreenerConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    preset: ScreenerPreset | None = None
    filters: list[dict[str, Any]] = Field(default_factory=list)
    filter_mode: FilterMode = Field(default="all", alias="filterMode")
    refresh_policy: RefreshPolicy = Field(default="on_session", alias="refreshPolicy")


class UniverseConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: UniverseMode
    fixed_list: list[str] | None = Field(default=None, alias="fixedList")
    index: str | None = None
    screener: ScreenerConfig | None = None
    excluded: list[str] = Field(default_factory=list)
    max_assets: int = Field(default=20, alias="maxAssets", ge=1, le=200)
    exit_on_drop: bool = Field(default=False, alias="exitOnDrop")

    @model_validator(mode="after")
    def _mode_requirements(self) -> UniverseConfig:
        if self.mode == "fixed" and not self.fixed_list:
            raise ValueError("fixedList is required when universe.mode is fixed")
        if self.mode == "index" and not self.index:
            raise ValueError("index is required when universe.mode is index")
        if self.mode == "screener" and self.screener is None:
            raise ValueError("screener is required when universe.mode is screener")
        return self


class EodFlattenConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool | None = None
    minutes_before_close: int = Field(default=15, alias="minutesBeforeClose", ge=1, le=120)


class RiskConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    capital: float = Field(..., gt=0)
    max_position_share_pct: float = Field(..., alias="maxPositionSharePct", ge=1, le=100)
    stop_loss_pct: float = Field(..., alias="stopLossPct", gt=0)
    take_profit_pct: float = Field(..., alias="takeProfitPct", gt=0)
    max_daily_loss: float = Field(..., alias="maxDailyLoss", gt=0)
    max_drawdown_pct: float = Field(default=50, alias="maxDrawdownPct", gt=0, le=100)
    max_concurrent_positions: int = Field(..., alias="maxConcurrentPositions", ge=1, le=10)
    broker_commission_pct: float = Field(..., alias="brokerCommissionPct", ge=0)
    tax_pct: float = Field(..., alias="taxPct", ge=0)
    slippage_pct: float = Field(default=0.5, alias="slippagePct", ge=0)
    stop_mode: StopMode = Field(default="soft", alias="stopMode")
    allocated_capital: float | None = Field(default=None, alias="allocatedCapital", gt=0)
    eod_flatten: EodFlattenConfig = Field(default_factory=EodFlattenConfig, alias="eodFlatten")

    @model_validator(mode="after")
    def _risk_ratio(self) -> RiskConfig:
        if self.stop_loss_pct >= self.take_profit_pct:
            raise ValueError("stopLossPct must be less than takeProfitPct")
        return self

    def eod_flatten_enabled_for(self, instrument_type: InstrumentType) -> bool:
        """MOEX stocks on by default; crypto/futures off unless explicitly enabled."""
        if self.eod_flatten.enabled is not None:
            return bool(self.eod_flatten.enabled)
        return instrument_type == "stock"


class PortfolioUpdaterConfigV4(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    config_version: Literal[4] = Field(default=CONFIG_VERSION_V4, alias="configVersion")
    schedule: ScheduleConfig


class TradingRobotConfigV4(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    config_version: Literal[4] = Field(default=CONFIG_VERSION_V4, alias="configVersion")
    core: CoreConfig
    strategy: StrategyConfig
    universe: UniverseConfig
    risk: RiskConfig

    @model_validator(mode="after")
    def _scalper_advanced_mode(self) -> TradingRobotConfigV4:
        if self.strategy.archetype == "scalper" and not self.core.advanced_mode:
            raise ValueError("scalper requires core.advancedMode=true")
        return self
