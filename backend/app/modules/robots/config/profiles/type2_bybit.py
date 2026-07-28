"""Profile schema: trading robot type=2, broker=bybit."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.robots.config.costs_crypto import CryptoCostsConfig
from app.modules.robots.config.risk_crypto import CryptoRiskConfig


class BybitBrokerConfig(BaseModel):
    testnet: bool = False
    instrument_category: Literal["spot", "linear", "inverse"] = "linear"
    position_mode: Literal["one_way", "hedge"] = "one_way"
    # 0 = no margin trading; >=1 = set ByBit leverage and allow margin sizing.
    leverage: int = Field(default=1, ge=0, le=125)


class CryptoUniverseRefresh(BaseModel):
    every_minutes: int = Field(default=60, ge=0, le=7 * 24 * 60)


class CryptoUniverseConfig(BaseModel):
    enabled: bool = True
    min_volume_24h_usd: float = 50_000_000.0
    min_last_price: float = Field(
        default=0.05,
        ge=0,
        description="Minimum last price in USDT; 0 disables the price filter",
    )
    max_spread_bps: float = 15.0
    min_funding_rate: float = Field(default=-0.0001, description="-0.01%")
    max_funding_rate: float = Field(default=0.0002, description="0.02%")
    min_open_interest_usd: float = 20_000_000.0
    min_lsr: float = 0.5
    max_lsr: float = 1.5
    min_rvol: float = 2.0
    min_atr_percent: float = 1.5
    max_atr_percent: float = 10.0
    lookback_days: int = Field(default=20, ge=1, le=365)
    funding_lookback_hours: int = Field(default=8, ge=1, le=72)
    refresh: CryptoUniverseRefresh = Field(default_factory=CryptoUniverseRefresh)


class CryptoSignalGenerationConfig(BaseModel):
    strategy: str = "reversion_to_ma"
    params: Dict[str, Any] = Field(default_factory=dict)
    data_source: Literal["bybit"] = "bybit"
    update_interval_seconds: int = Field(default=10, ge=1, le=3600)


class Type2BybitConfig(BaseModel):
    config_version: int = Field(default=3, ge=2, le=3)
    schema_profile: Literal["type2_bybit"] = "type2_bybit"
    broker_type: Literal["bybit"] = "bybit"
    market_profile: Literal["crypto"] = "crypto"
    instrument_id_type: Literal["symbol"] = "symbol"
    universe_mode: Optional[Literal["fixed", "auto"]] = None
    instruments: List[str] = Field(default_factory=list)
    bybit: BybitBrokerConfig = Field(default_factory=BybitBrokerConfig)
    crypto_universe: CryptoUniverseConfig = Field(default_factory=CryptoUniverseConfig)
    signal_generation: CryptoSignalGenerationConfig = Field(default_factory=CryptoSignalGenerationConfig)
    allowed_symbols: List[str] = Field(default_factory=list)
    risk: CryptoRiskConfig = Field(default_factory=CryptoRiskConfig)
    costs: CryptoCostsConfig = Field(default_factory=CryptoCostsConfig)

    # Legacy mirror for compatibility with current runtime paths.
    strategy: str | None = None
    strategy_params: Dict[str, Any] | None = None

    @field_validator("instruments", "allowed_symbols", mode="before")
    @classmethod
    def _norm_symbols(cls, v: Any) -> List[str]:
        if not v:
            return []
        return sorted({str(x).strip().upper() for x in v if str(x).strip()})

    @model_validator(mode="after")
    def _normalize_crypto_universe_mode(self) -> "Type2BybitConfig":
        has_symbols = bool(self.allowed_symbols or self.instruments)
        mode = self.universe_mode
        if mode is None:
            if has_symbols:
                mode = "fixed"
            elif self.crypto_universe.enabled:
                mode = "auto"
            else:
                mode = "fixed"
        if mode == "auto" and not self.crypto_universe.enabled:
            raise ValueError("universe_mode=auto requires crypto_universe.enabled=true")
        if mode == "fixed" and not has_symbols:
            raise ValueError("universe_mode=fixed requires allowed_symbols or instruments")
        object.__setattr__(self, "universe_mode", mode)
        return self

    @model_validator(mode="after")
    def _strip_moex_eod_flatten(self) -> "Type2BybitConfig":
        from app.modules.robots.universe import strip_moex_eod_flatten_params

        if isinstance(self.strategy_params, dict):
            object.__setattr__(
                self,
                "strategy_params",
                strip_moex_eod_flatten_params(self.strategy_params),
            )
        sg = self.signal_generation
        if sg is not None and isinstance(sg.params, dict) and sg.params:
            cleaned = strip_moex_eod_flatten_params(sg.params)
            object.__setattr__(
                self,
                "signal_generation",
                sg.model_copy(update={"params": cleaned}),
            )
        return self


__all__ = [
    "BybitBrokerConfig",
    "CryptoUniverseRefresh",
    "CryptoUniverseConfig",
    "CryptoSignalGenerationConfig",
    "Type2BybitConfig",
]

