"""Universe Service HTTP routes (Stage 1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from app.modules.robots_v2.universe import schemas
from app.modules.robots_v2.universe.service import universe_service

router = APIRouter(prefix="/v2/universe", tags=["Universe Service V2"])


def _require_v2_enabled() -> None:
    if not settings.ROBOTS_V2_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Robots v2 contour is disabled (ROBOTS_V2_ENABLED=false)",
        )


@router.post("/resolve", response_model=schemas.ResolvedUniverse)
async def resolve_universe(
    request: schemas.UniverseResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return await universe_service.resolve(
        db,
        current_user.id,
        token_id=request.token_id,
        instrument_type=request.instrument_type,
        universe_raw=request.universe,
        robot_id=request.robot_id,
    )


@router.post("/validate-tickers", response_model=schemas.ValidateTickersResponse)
async def validate_tickers(
    request: schemas.ValidateTickersRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return await universe_service.validate_tickers(
        db,
        current_user.id,
        token_id=request.token_id,
        instrument_type=request.instrument_type,
        tickers=request.tickers,
    )


@router.get("/indices", response_model=schemas.IndexListResponse)
async def list_indices(
    market: str = Query(default="moex", pattern="^(moex|crypto|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    items = await universe_service.list_indices(db, current_user.id, market=market)
    return schemas.IndexListResponse(
        items=[schemas.IndexListItem.model_validate(item) for item in items],
    )
