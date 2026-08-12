"""HTTP API for robots v2 greenfield contour."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from app.modules.robots_v2 import schemas, service
from app.modules.robots_v2.backtest import backtest_service
from app.modules.robots_v2.backtest.schemas import (
    RobotV2BacktestAsyncAccepted,
    RobotV2BacktestDetailsResponse,
    RobotV2BacktestRequest,
    RobotV2BacktestStatusResponse,
)
from app.modules.robots_v2.engine.event_bus import event_bus
from app.modules.robots_v2.universe.schemas import UniversePreview
from app.modules.robots_v2.universe.service import universe_service

router = APIRouter(prefix="/v2/robots", tags=["Trading Robots V2"])


def _require_v2_enabled() -> None:
    if not settings.ROBOTS_V2_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Robots v2 contour is disabled (ROBOTS_V2_ENABLED=false)",
        )


@router.post("/data", response_model=schemas.RobotV2ListResponse)
async def list_robots(
    request: schemas.RobotV2ListRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    items = service.robots_v2_service.list_robots(db, current_user.id, request)
    return schemas.RobotV2ListResponse(items=items, total=len(items))


@router.post("/create", response_model=schemas.RobotV2Response)
async def create_or_update_robot(
    request: schemas.RobotV2CreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return service.robots_v2_service.create_or_update(db, current_user.id, request)


@router.get("/{robot_id}", response_model=schemas.RobotV2Response)
async def get_robot(
    robot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return service.robots_v2_service.get_robot(db, current_user.id, robot_id)


@router.post("/delete")
async def delete_robot(
    request: schemas.RobotV2DeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return service.robots_v2_service.delete_robot(db, current_user.id, request.robot_id)


@router.post("/{robot_id}/clone", response_model=schemas.RobotV2Response)
async def clone_robot(
    robot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return service.robots_v2_service.clone_robot(db, current_user.id, robot_id)


@router.get("/{robot_id}/logs")
async def get_robot_logs(
    robot_id: int,
    limit: int = 100,
    event_type: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    _ = service.robots_v2_service.get_robot(db, current_user.id, robot_id)
    items = event_bus.recent(robot_id, limit=min(max(limit, 1), 500), event_type=event_type)
    return {"robotId": robot_id, "items": items, "total": len(items)}


@router.post("/validate", response_model=schemas.RobotV2ValidateResponse)
async def validate_robot_config(
    request: schemas.RobotV2ValidateRequest,
    _: User = Depends(get_current_user),
    __: None = Depends(_require_v2_enabled),
):
    return service.robots_v2_service.validate(request)


@router.post("/preview-universe", response_model=UniversePreview)
async def preview_universe(
    request: schemas.RobotV2PreviewUniverseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return await universe_service.preview(
        db,
        current_user.id,
        token_id=request.token_id,
        instrument_type=request.instrument_type,
        universe_raw=request.universe,
        page=request.page,
        page_size=request.page_size,
    )


@router.post(
    "/backtest",
    response_model=None,
    responses={
        200: {"model": RobotV2BacktestDetailsResponse},
        202: {"model": RobotV2BacktestAsyncAccepted},
    },
)
async def run_v2_backtest(
    request: RobotV2BacktestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    rec, enqueued = await backtest_service.start(db, current_user.id, request)
    if enqueued:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=RobotV2BacktestAsyncAccepted(
                run_id=rec.run_id,
                message=f"Poll GET /api/v2/robots/backtest/runs/{rec.run_id}/status",
            ).model_dump(),
        )
    details = await backtest_service.get_details(rec.run_id, user_id=current_user.id)
    return details


@router.get("/backtest/runs/{run_id}/status", response_model=RobotV2BacktestStatusResponse)
async def get_v2_backtest_status(
    run_id: int,
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return await backtest_service.get_status(run_id, user_id=current_user.id)


@router.get("/backtest/runs/{run_id}", response_model=RobotV2BacktestDetailsResponse)
async def get_v2_backtest_details(
    run_id: int,
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return await backtest_service.get_details(run_id, user_id=current_user.id)


@router.post("/backtest/runs/{run_id}/cancel")
async def cancel_v2_backtest(
    run_id: int,
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    rec = await backtest_service.cancel(run_id, user_id=current_user.id)
    return {"run_id": rec.run_id, "cancel_requested": True, "status": rec.status}


@router.post("/change_status", response_model=schemas.RobotV2Response)
async def change_robot_status(
    request: schemas.RobotV2ChangeStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return service.robots_v2_service.change_status(db, current_user.id, request)


@router.post("/{robot_id}/start", response_model=schemas.RobotV2Response)
async def start_robot(
    robot_id: int,
    request: schemas.RobotV2StartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return await service.robots_v2_service.start_robot(db, current_user.id, robot_id, request)


@router.post("/{robot_id}/stop", response_model=schemas.RobotV2Response)
async def stop_robot(
    robot_id: int,
    stop_mode: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    return await service.robots_v2_service.stop_robot(db, current_user.id, robot_id, stop_mode)


@router.get("/{robot_id}/status", response_model=schemas.RobotV2StatusResponse)
async def get_robot_status(
    robot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(_require_v2_enabled),
):
    payload = service.robots_v2_service.get_status(db, current_user.id, robot_id)
    return schemas.RobotV2StatusResponse.model_validate(payload)


@router.websocket("/{robot_id}/stream")
async def robot_stream(websocket: WebSocket, robot_id: int):
    if not settings.ROBOTS_V2_ENABLED:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    queue = event_bus.subscribe(robot_id)
    await websocket.send_text(json.dumps({"type": "connected", "robotId": robot_id}))
    # Seed equity curve from session + recent cycle events (oldest → newest)
    try:
        from app.modules.robots_v2.engine.session_manager import session_manager

        snap = session_manager.status(robot_id)
        if snap and snap.equity_curve:
            await websocket.send_text(json.dumps({
                "type": "equity_snapshot",
                "robotId": robot_id,
                "points": snap.equity_curve,
            }, default=str))
        recent = list(reversed(event_bus.recent(robot_id, limit=100, event_type="cycle")))
        for ev in recent:
            await websocket.send_text(json.dumps(ev, default=str))
    except Exception:
        pass
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_text(json.dumps(event, default=str))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping", "robotId": robot_id}))
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(robot_id, queue)
