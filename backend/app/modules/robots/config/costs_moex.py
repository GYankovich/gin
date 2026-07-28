"""Typed MOEX costs config for profile-based validation."""

from __future__ import annotations

from pydantic import BaseModel


class MoexCostsConfig(BaseModel):
    """MOEX costs params (type2_tinvest profile)."""
    broker_commission_rate: float = 0.0005
    ndfl_rate: float = 0.15


__all__ = ["MoexCostsConfig"]
