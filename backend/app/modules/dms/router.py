from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

#///EPIC Backtesting.ITEM DMS.TOPIC Data Management Endpoints [1]
#/// Роутер DMS: подписки, снапшоты, preview pipeline, инициализация дня и логи
#/// фильтрации; используется как фундамент отбора бумаг для торговли/бэктеста.
from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User

from . import schemas
from .service import dms_service

router = APIRouter(prefix="/dms", tags=["DMS"])


@router.post("/subscribe", response_model=schemas.DmsSubscribeResponse)
async def subscribe(
    body: schemas.DmsSubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await dms_service.subscribe(db, current_user.id, body)
    return schemas.DmsSubscribeResponse(**data)


@router.get("/subscriptions", response_model=list[schemas.DmsSubscriptionItem])
async def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await dms_service.list_subscriptions(db, current_user.id)
    return [schemas.DmsSubscriptionItem(**r) for r in rows]


@router.get("/snapshots", response_model=list[schemas.MarketSnapshotItem])
async def list_snapshots(
    board: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await dms_service.list_snapshots(db, board=board)
    return [schemas.MarketSnapshotItem(**r) for r in rows]


@router.post("/snapshots/create", response_model=schemas.DmsCreateSnapshotResponse)
async def create_snapshot(
    body: schemas.DmsCreateSnapshotRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await dms_service.create_snapshot(
        db=db,
        board=body.board,
        ttl_minutes=body.ttl_minutes,
        is_manual=body.is_manual,
        user_id=current_user.id,
    )
    return schemas.DmsCreateSnapshotResponse(**data)


@router.post("/process-queue", response_model=schemas.DmsProcessQueueResponse)
async def process_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await dms_service.process_pending_subscriptions(db)
    return schemas.DmsProcessQueueResponse(**data)


@router.post("/maintenance/cleanup", response_model=schemas.DmsCleanupResponse)
async def cleanup(
    older_than_days: int = Query(default=3, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await dms_service.cleanup_old_snapshots(db, older_than_days=older_than_days)
    return schemas.DmsCleanupResponse(**data)


@router.post("/pipeline/preview", response_model=schemas.DmsPipelinePreviewResponse)
async def preview_pipeline(
    body: schemas.DmsPipelinePreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await dms_service.preview_pipeline(
        db=db,
        user_id=current_user.id,
        robot_id=body.robot_id,
        board=body.board,
        filters=body.filters,
        mode=body.mode,
    )
    return schemas.DmsPipelinePreviewResponse(**data)


@router.post("/initialize-day", response_model=schemas.DmsInitializeDayResponse)
async def initialize_day(
    body: schemas.DmsInitializeDayRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await dms_service.initialize_trading_day(
        db=db,
        user_id=current_user.id,
        robot_id=body.robot_id,
        board=body.board,
        force_refresh_snapshot=body.force_refresh_snapshot,
    )
    return schemas.DmsInitializeDayResponse(**data)


@router.get("/daily-universe", response_model=schemas.DailyUniverseResponse)
async def list_daily_universe(
    robot_id: Optional[int] = Query(default=None),
    trade_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await dms_service.list_daily_universe(db, current_user.id, robot_id=robot_id, trade_date=trade_date)
    return schemas.DailyUniverseResponse(**data)


@router.get("/filter-log", response_model=schemas.DmsFilterLogResponse)
async def filter_log(
    robot_id: Optional[int] = Query(default=None),
    trade_date: Optional[date] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await dms_service.get_filter_log(
        db=db,
        user_id=current_user.id,
        robot_id=robot_id,
        trade_date=trade_date,
        limit=limit,
    )
    return schemas.DmsFilterLogResponse(**data)
