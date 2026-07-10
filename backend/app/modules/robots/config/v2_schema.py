"""Схема конфига торгового робота v2: П1 → П2 → П3."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

CONFIG_VERSION_V2 = 2

HistoricalSource = Literal["moex", "tinvest"]
HistoricalUniverse = Literal["tqbr_all", "fixed", "from_list"]
PaperSelectionInput = Literal["candidate_pool", "fixed", "tqbr_all", "allowed_figis"]
PipelineMode = Literal["ALL", "ANY"]

# Фильтры по историческим свечам (П1).
HISTORICAL_FILTER_TYPES = frozenset({
    "atr",
    "atr_percent",
    "volatility",
    "realized_volatility",
    "min_avg_volume",
    "volume_avg",
})

# Фильтры по снапшоту / оперативным полям (П2).
PAPER_FILTER_TYPES = frozenset({
    "security_status",
    "trading_status",
    "volume",
    "num_trades",
    "gap",
    "spread",
    "turnover",
    "gap_retention",
    "min_step_ratio",
    "dividend",
})


class RefreshSchedule(BaseModel):
    """Расписание пересчёта контура."""

    every_minutes: int = Field(
        default=0,
        ge=0,
        le=7 * 24 * 60,
        description="0 — только вручную / daily_at_msk",
    )
    only_trading_hours: bool = True
    daily_at_msk: Optional[str] = Field(
        default=None,
        description="HH:MM MSK, если задан — ежедневный пересчёт (П1)",
    )


class HistoricalScreeningConfig(BaseModel):
    """П1: исторический скрининг (массовый пул candidate_pool)."""

    enabled: bool = True
    source: HistoricalSource = "moex"
    board: str = "TQBR"
    universe: HistoricalUniverse = "tqbr_all"
    fixed_tickers: List[str] = Field(default_factory=list)
    interval: str = Field(
        default="CANDLE_INTERVAL_10_MIN",
        description="Интервал свечей MOEX/T-Invest для lookback",
    )
    lookback_days: int = Field(default=14, ge=1, le=3650)
    filters: List[Dict[str, Any]] = Field(default_factory=list)
    refresh: RefreshSchedule = Field(
        default_factory=lambda: RefreshSchedule(every_minutes=0, daily_at_msk="07:00"),
    )

    @field_validator("fixed_tickers", mode="before")
    @classmethod
    def _norm_tickers(cls, v: Any) -> List[str]:
        if not v:
            return []
        return sorted({str(x).strip().upper() for x in v if str(x).strip()})


class PaperSelectionConfig(BaseModel):
    """П2: отбор бумаг на торговую сессию (tradable_universe)."""

    enabled: bool = True
    input: PaperSelectionInput = "candidate_pool"
    fixed_tickers: List[str] = Field(default_factory=list)
    mode: PipelineMode = "ALL"
    filters: List[Dict[str, Any]] = Field(default_factory=list)
    refresh: RefreshSchedule = Field(
        default_factory=lambda: RefreshSchedule(every_minutes=30, only_trading_hours=True),
    )

    @field_validator("fixed_tickers", mode="before")
    @classmethod
    def _norm_tickers(cls, v: Any) -> List[str]:
        if not v:
            return []
        return sorted({str(x).strip().upper() for x in v if str(x).strip()})


class SignalGenerationConfig(BaseModel):
    """П3: генерация сигналов и live-данные."""

    strategy: str = "grain_seed"
    params: Dict[str, Any] = Field(default_factory=dict)
    data_source: Literal["tinvest", "vtb", "alfa"] = "tinvest"
    update_interval_seconds: int = Field(default=10, ge=1, le=3600)
    indicator_update_schedule: Dict[str, str] = Field(
        default_factory=lambda: {
            "CANDLE_INTERVAL_DAY": "10:00 MSK",
            "CANDLE_INTERVAL_HOUR": "every hour at :05",
        },
    )


class TradingRobotConfigV2(BaseModel):
    """Конфиг type=2, версия 2 (источник правды при config_version >= 2)."""

    config_version: int = Field(default=CONFIG_VERSION_V2, ge=2, le=2)
    historical_screening: HistoricalScreeningConfig = Field(
        default_factory=HistoricalScreeningConfig,
    )
    paper_selection: PaperSelectionConfig = Field(default_factory=PaperSelectionConfig)
    signal_generation: SignalGenerationConfig = Field(default_factory=SignalGenerationConfig)
    allowed_figis: List[str] = Field(
        default_factory=list,
        description="Результат П2 (tradable_universe), обновляется рантаймом",
    )
    risk: Dict[str, Any] = Field(default_factory=dict)
    costs: Dict[str, Any] = Field(default_factory=dict)
    execution_model: Optional[Dict[str, Any]] = None

    # Legacy-зеркало (синхронизируется при save/validate, читают старые пути).
    strategy: Optional[str] = None
    strategy_params: Optional[Dict[str, Any]] = None
    broker_type: Optional[str] = None
    pipeline: Optional[Dict[str, Any]] = None
    universe_mode: Optional[str] = None
    fixed_tickers: List[str] = Field(default_factory=list)
    universe_refresh_minutes: int = Field(default=0, ge=0, le=24 * 60)
    update_interval_seconds: Optional[int] = None
    indicator_update_schedule: Optional[Dict[str, str]] = None
