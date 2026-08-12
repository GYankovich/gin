"""Dry-run evaluate API for Strategy Runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.security import get_current_user
from app.modules.auth.models import User
from app.modules.robots.trading.contracts import Candle, Position, Signal
from app.modules.robots_v2.config.v4_schema import StrategyConfig
from app.modules.robots_v2.strategy.registry import list_archetypes
from app.modules.robots_v2.strategy.runtime import strategy_runtime
from app.modules.robots_v2.strategy.schemas import ArchetypeInfo, OrderFlowSnapshot, StrategyContext

router = APIRouter(prefix="/v2/strategy", tags=["Strategy Runtime V2"])


def _require_v2_enabled() -> None:
    if not settings.ROBOTS_V2_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Robots v2 contour is disabled (ROBOTS_V2_ENABLED=false)",
        )


class StrategyEvaluateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: int = Field(default=0, alias="sessionId")
    robot_id: int = Field(default=0, alias="robotId")
    strategy: dict[str, Any]
    universe: list[str]
    last_price: dict[str, float] = Field(default_factory=dict, alias="lastPrice")
    candles: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    atr: dict[str, float] = Field(default_factory=dict)
    order_flow: dict[str, dict[str, Any]] | None = Field(default=None, alias="orderFlow")
    open_positions: list[dict[str, Any]] = Field(default_factory=list, alias="openPositions")
    mode: str = "paper"
    triggered_by: str = Field(default="bar_close", alias="triggeredBy")
    instrument_type: str = Field(default="stock", alias="instrumentType")
    allow_short: bool = Field(default=False, alias="allowShort")
    ws_healthy: bool = Field(default=True, alias="wsHealthy")


class StrategyEvaluateResponse(BaseModel):
    signals: list[Signal]
    count: int


class ArchetypeListResponse(BaseModel):
    items: list[ArchetypeInfo]


def _parse_candles(raw: dict[str, list[dict[str, Any]]]) -> dict[str, list[Candle]]:
    out: dict[str, list[Candle]] = {}
    for ticker, rows in raw.items():
        parsed: list[Candle] = []
        for row in rows:
            if isinstance(row, Candle):
                parsed.append(row)
            else:
                parsed.append(Candle.from_tinvest_dict(row, secid=ticker.upper()))
        out[ticker.upper()] = parsed
    return out


def _parse_positions(raw: list[dict[str, Any]]) -> list[Position]:
    positions: list[Position] = []
    for row in raw:
        side = str(row.get("side") or "LONG").upper()
        positions.append(Position(
            side="SHORT" if side == "SHORT" else "LONG",
            quantity=int(row.get("quantity") or 0),
            avg_entry_price=float(row.get("avgEntryPrice") or row.get("avg_entry_price") or 0),
            secid=str(row.get("secid") or row.get("ticker") or "").upper() or None,
            figi=row.get("figi"),
            current_price=float(row.get("currentPrice") or row.get("current_price") or 0),
        ))
    return positions


@router.get("/archetypes", response_model=ArchetypeListResponse)
async def get_archetypes(
    _: User = Depends(get_current_user),
    __: None = Depends(_require_v2_enabled),
):
    return ArchetypeListResponse(items=list_archetypes())


@router.post("/evaluate", response_model=StrategyEvaluateResponse)
async def evaluate_strategy(
    request: StrategyEvaluateRequest,
    _: User = Depends(get_current_user),
    __: None = Depends(_require_v2_enabled),
):
    config = StrategyConfig.model_validate(request.strategy)
    session_id = request.session_id or request.robot_id or 0
    order_flow = None
    if request.order_flow:
        order_flow = {
            k.upper(): OrderFlowSnapshot.model_validate(v)
            for k, v in request.order_flow.items()
        }
    ctx = StrategyContext(
        robot_id=request.robot_id,
        cycle_id=uuid4(),
        config=config,
        universe=[t.upper() for t in request.universe],
        last_price={k.upper(): float(v) for k, v in request.last_price.items()},
        candles=_parse_candles(request.candles),
        atr={k.upper(): float(v) for k, v in request.atr.items()},
        open_positions=_parse_positions(request.open_positions),
        mode=request.mode,  # type: ignore[arg-type]
        now=datetime.now(timezone.utc),
        triggered_by=request.triggered_by,  # type: ignore[arg-type]
        instrument_type=request.instrument_type,
        order_flow=order_flow,
        ws_healthy=request.ws_healthy,
        allow_short=request.allow_short,
    )
    signals = strategy_runtime.evaluate(session_id, ctx)
    return StrategyEvaluateResponse(signals=signals, count=len(signals))
