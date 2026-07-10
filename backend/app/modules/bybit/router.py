"""ByBit read-only REST endpoints for UI."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user
from app.core.database import get_db
from app.modules.auth.models import User
from app.modules.bybit.http_client import BybitApiError
from app.modules.bybit.live_smoke import run_bybit_live_smoke
from app.modules.bybit.schemas import BybitFundingRateResponse
from app.modules.bybit.schemas import BybitInstrumentsResponse
from app.modules.bybit.schemas import BybitLiveSmokeResponse
from app.modules.bybit.schemas import BybitUniverseScreeningPreviewRequest
from app.modules.bybit.schemas import BybitUniverseScreeningPreviewResponse
from app.modules.bybit.service import bybit_market_service
from app.modules.robots.crypto_universe import _find_active_bybit_token
from sqlalchemy.orm import Session

router = APIRouter(prefix="/bybit", tags=["bybit"])


@router.get(
    "/funding-rate",
    response_model=BybitFundingRateResponse,
    summary="Current ByBit funding rate (read-only)",
)
async def get_bybit_funding_rate(
    symbol: str = Query(..., min_length=3, max_length=32, description="Trading pair, e.g. BTCUSDT"),
    instrument_category: Literal["spot", "linear", "inverse"] = Query(
        "linear",
        description="ByBit market category",
    ),
    testnet: bool = Query(False, description="Ignored; mainnet only"),
    current_user: User = Depends(get_current_user),
) -> BybitFundingRateResponse:
    """Funding rate for crypto UI panels (no broker keys required)."""
    _ = current_user
    try:
        return await bybit_market_service.get_funding_rate(
            symbol=symbol,
            instrument_category=instrument_category,
            testnet=testnet,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BybitApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/instruments",
    response_model=BybitInstrumentsResponse,
    summary="ByBit tradable instruments (read-only)",
)
async def get_bybit_instruments(
    category: Literal["spot", "linear", "inverse"] = Query(
        "linear",
        description="ByBit market category",
    ),
    quote_coin: str | None = Query(None, description="Filter by quote coin, e.g. USDT"),
    testnet: bool = Query(False, description="Ignored; mainnet only"),
    current_user: User = Depends(get_current_user),
) -> BybitInstrumentsResponse:
    """Instrument list for crypto UI symbol picker (no broker keys required)."""
    _ = current_user
    try:
        return await bybit_market_service.get_instruments(
            category=category,
            quote_coin=quote_coin,
            testnet=testnet,
        )
    except BybitApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/universe/screening-preview",
    response_model=BybitUniverseScreeningPreviewResponse,
    summary="Live crypto universe screening preview (read-only)",
)
async def preview_bybit_universe_screening(
    body: BybitUniverseScreeningPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BybitUniverseScreeningPreviewResponse:
    """Текущий размер universe по фильтрам (без сохранения в робота)."""
    try:
        return await bybit_market_service.preview_universe_screening(db, current_user.id, body)
    except BybitApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/live-smoke",
    response_model=BybitLiveSmokeResponse,
    summary="ByBit mainnet live smoke (wallet + positions, no orders)",
)
async def bybit_live_smoke(
    symbol: str = Query("BTCUSDT", min_length=3, max_length=32),
    instrument_category: Literal["spot", "linear", "inverse"] = Query("linear"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BybitLiveSmokeResponse:
    """Проверка live-контура ByBit для текущего пользователя (mainnet, без ордеров)."""
    token_row = _find_active_bybit_token(db, current_user.id)
    if not token_row:
        raise HTTPException(
            status_code=404,
            detail="Активный ByBit токен не найден (api_tokens с secret)",
        )
    try:
        payload = await run_bybit_live_smoke(
            str(token_row.get("token") or ""),
            {"token_secret": str(token_row.get("token_secret") or "")},
            symbol=symbol,
            instrument_category=instrument_category,
        )
        return BybitLiveSmokeResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


__all__ = ["router"]
