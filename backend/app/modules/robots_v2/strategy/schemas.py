"""Strategy Runtime contracts (greenfield Part IV)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.modules.robots.trading.contracts import Candle, Position, Signal
from app.modules.robots_v2.config.v4_schema import StrategyArchetype, StrategyConfig, TradingMode

TriggeredBy = Literal["poll", "bar_close", "price_tick"]
DataRequirement = Literal[
    "last_price",
    "candles",
    "bar_close_events",
    "websocket_trades",
    "orderbook_delta",
    "atr",
]


class OrderFlowSnapshot(BaseModel):
    buy_volume: float = Field(alias="buyVolume")
    sell_volume: float = Field(alias="sellVolume")
    delta_pct: float = Field(alias="deltaPct")
    window_sec: int = Field(alias="windowSec")
    tick_count: int = Field(default=0, alias="tickCount")
    trade_count: int = Field(default=0, alias="tradeCount")
    has_real_trades: bool = Field(default=False, alias="hasRealTrades")
    flow_source: Literal["trades", "inferred"] = Field(default="inferred", alias="flowSource")

    model_config = ConfigDict(populate_by_name=True)


@dataclass
class StrategyContext:
    robot_id: int
    cycle_id: UUID
    config: StrategyConfig
    universe: list[str]
    last_price: dict[str, float]
    candles: dict[str, list[Candle]]
    atr: dict[str, float]
    open_positions: list[Position]
    mode: TradingMode
    now: datetime
    triggered_by: TriggeredBy
    instrument_type: str = "stock"
    order_flow: dict[str, OrderFlowSnapshot] | None = None
    ws_healthy: bool = True
    allow_short: bool = False
    take_profit_pct: float | None = None
    stop_loss_pct: float | None = None
    broker_commission_rate: float | None = None
    tax_pct: float | None = None


@dataclass
class StrategySessionState:
    archetype: StrategyArchetype
    per_ticker: dict[str, dict[str, Any]] = field(default_factory=dict)


class ArchetypeInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    archetype: StrategyArchetype
    required_data: list[DataRequirement] = Field(alias="requiredData")
    warmup_bars: int = Field(alias="warmupBars")
    entry_triggers: list[TriggeredBy] = Field(alias="entryTriggers")
    requires_websocket: bool = Field(default=False, alias="requiresWebsocket")
