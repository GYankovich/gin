"""OsEngine live ingest HTTP API (bridge → GIN DB).

Auth: header ``X-OsEngine-Token`` == settings.OSENGINE_INGEST_TOKEN
(если токен пуст и ENVIRONMENT!=production — allow; иначе 401).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.modules.osengine import ingest as ingest_svc
from app.modules.osengine.schemas import (
    IngestCandlesRequest,
    IngestDepthRequest,
    IngestResult,
    IngestTicksRequest,
    LiveStatusResponse,
)

router = APIRouter(prefix="/osengine", tags=["osengine"])


def _require_ingest_token(x_osengine_token: Optional[str] = Header(default=None, alias="X-OsEngine-Token")) -> None:
    expected = (settings.OSENGINE_INGEST_TOKEN or "").strip()
    if not expected:
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OSENGINE_INGEST_TOKEN is not configured",
            )
        return
    if (x_osengine_token or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OsEngine ingest token")


@router.post("/ingest/candles", response_model=IngestResult, dependencies=[Depends(_require_ingest_token)])
def ingest_candles(body: IngestCandlesRequest, db: Session = Depends(get_db)) -> IngestResult:
    n = ingest_svc.ingest_candles(
        db,
        body.candles,
        subscribed_instruments=body.subscribed_instruments,
    )
    db.commit()
    return IngestResult(accepted=n, stream="candles", market=settings.OSENGINE_MARKET_KEY)


@router.post("/ingest/ticks", response_model=IngestResult, dependencies=[Depends(_require_ingest_token)])
def ingest_ticks(body: IngestTicksRequest, db: Session = Depends(get_db)) -> IngestResult:
    n = ingest_svc.ingest_ticks(
        db,
        body.ticks,
        subscribed_instruments=body.subscribed_instruments,
    )
    db.commit()
    return IngestResult(accepted=n, stream="ticks", market=settings.OSENGINE_MARKET_KEY)


@router.post("/ingest/depth", response_model=IngestResult, dependencies=[Depends(_require_ingest_token)])
def ingest_depth(body: IngestDepthRequest, db: Session = Depends(get_db)) -> IngestResult:
    n = ingest_svc.ingest_depth(
        db,
        body.books,
        subscribed_instruments=body.subscribed_instruments,
    )
    db.commit()
    return IngestResult(accepted=n, stream="depth", market=settings.OSENGINE_MARKET_KEY)


@router.get("/live/status", response_model=LiveStatusResponse)
def live_status(db: Session = Depends(get_db)) -> LiveStatusResponse:
    st = ingest_svc.read_live_status(db)
    return LiveStatusResponse(
        enabled=st.enabled,
        bridge_connected=st.bridge_connected,
        subscribed_instruments=st.subscribed_instruments,
        last_candle_at=st.last_candle_at,
        last_tick_at=st.last_tick_at,
        last_depth_at=st.last_depth_at,
        lag_seconds=st.lag_seconds,
        detail=st.detail,
    )
