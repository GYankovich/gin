"""Profile schema: portfolio robot type=1, broker=tinvest."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Type1TinvestConfig(BaseModel):
    config_version: int = Field(default=3, ge=2, le=3)
    schema_profile: Literal["type1_tinvest"] = "type1_tinvest"
    broker_type: Literal["tinvest"] = "tinvest"


__all__ = ["Type1TinvestConfig"]
