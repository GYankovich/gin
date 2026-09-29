"""ARCH-05 Phase C Control API: /api/compute/v1."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from app.modules.compute.schemas import (
    ComputeBatchAccepted,
    ComputeBatchCreateRequest,
    ComputeBatchStatusResponse,
    ComputeCancelResponse,
    ComputeCompareRequest,
    ComputeQueueMetrics,
    ComputeRunAccepted,
    ComputeRunCreateRequest,
)
from app.modules.compute.service import compute_service
from app.modules.robots_v2.backtest.schemas import (
    RobotV2BacktestCompareResponse,
    RobotV2BacktestDetailsResponse,
    RobotV2BacktestListResponse,
    RobotV2BacktestStatusResponse,
)

router = APIRouter(prefix="/compute/v1", tags=["compute-v1"])


@router.post(
    "/runs",
    response_model=ComputeRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(
    body: ComputeRunCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    accepted = await compute_service.create_run(
        db, current_user.id, body, idempotency_key=idempotency_key,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=accepted.model_dump(),
    )


@router.get("/runs", response_model=RobotV2BacktestListResponse)
async def list_runs(
    robot_id: int | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await compute_service.list_runs(
        db, user_id=current_user.id, robot_id=robot_id, limit=limit, offset=offset,
    )


@router.get("/runs/{run_id}/status", response_model=RobotV2BacktestStatusResponse)
async def get_run_status(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await compute_service.get_run_status(run_id, user_id=current_user.id, db=db)


@router.get("/runs/{run_id}", response_model=RobotV2BacktestDetailsResponse)
async def get_run_details(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await compute_service.get_run_details(run_id, user_id=current_user.id, db=db)


@router.post("/runs/{run_id}/cancel", response_model=ComputeCancelResponse)
async def cancel_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await compute_service.cancel_run(run_id, user_id=current_user.id, db=db)


@router.post("/runs/compare", response_model=RobotV2BacktestCompareResponse)
async def compare_runs(
    body: ComputeCompareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await compute_service.compare_runs(
        db,
        user_id=current_user.id,
        base_run_id=body.base_run_id,
        compare_run_id=body.compare_run_id,
    )


@router.post(
    "/batches",
    response_model=ComputeBatchAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_batch(
    body: ComputeBatchCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    accepted = await compute_service.create_batch(
        db, current_user.id, body, idempotency_key=idempotency_key,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=accepted.model_dump(),
    )


@router.get("/batches/{batch_id}", response_model=ComputeBatchStatusResponse)
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return compute_service.get_batch(db, batch_id=batch_id, user_id=current_user.id)


@router.post("/batches/{batch_id}/cancel", response_model=ComputeCancelResponse)
async def cancel_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await compute_service.cancel_batch(
        db, batch_id=batch_id, user_id=current_user.id,
    )


@router.get("/metrics/queue", response_model=ComputeQueueMetrics)
def queue_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return compute_service.queue_metrics(db)
