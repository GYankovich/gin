"""Profile schema: trading robot type=2, broker=tinvest."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.modules.robots.config.costs_moex import MoexCostsConfig
from app.modules.robots.config.risk_moex import MoexRiskConfig
from app.modules.robots.config.v2_schema import TradingRobotConfigV2


class Type2TinvestConfig(TradingRobotConfigV2):
    """Профиль type2_tinvest (v3 identity + v2 pipeline blocks)."""

    config_version: Literal[3] = 3
    schema_profile: Literal["type2_tinvest"] = "type2_tinvest"
    broker_type: Literal["tinvest", "sandbox"] = "tinvest"
    instrument_id_type: Literal["figi"] = "figi"
    risk: MoexRiskConfig = Field(default_factory=MoexRiskConfig)
    costs: MoexCostsConfig = Field(default_factory=MoexCostsConfig)


__all__ = ["Type2TinvestConfig"]