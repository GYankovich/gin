"""Profile schema: portfolio robot type=1, broker=bybit."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Type1BybitBrokerConfig(BaseModel):
    testnet: bool = False
    account_type: Literal["UNIFIED", "CONTRACT", "SPOT"] = "UNIFIED"


class Type1BybitConfig(BaseModel):
    config_version: int = Field(default=3, ge=2, le=3)
    schema_profile: Literal["type1_bybit"] = "type1_bybit"
    broker_type: Literal["bybit"] = "bybit"
    bybit: Type1BybitBrokerConfig = Field(default_factory=Type1BybitBrokerConfig)


__all__ = ["Type1BybitBrokerConfig", "Type1BybitConfig"]

