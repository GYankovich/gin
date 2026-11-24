"""Typed crypto costs config for ByBit trading profile."""

from __future__ import annotations

from pydantic import BaseModel


class CryptoCostsConfig(BaseModel):
    maker_fee_rate: float = 0.0001
    taker_fee_rate: float = 0.0006
    funding_rate_enabled: bool = True
    funding_mode: str = "historical"


__all__ = ["CryptoCostsConfig"]

