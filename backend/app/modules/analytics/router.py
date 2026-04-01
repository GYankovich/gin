# app/modules/analytics/router.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from . import schemas
from .service import analytics_service

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/accounts", response_model=List[schemas.AccountSummary])
def get_accounts(
        include_inactive: bool = Query(False, description="Включать закрытые счета"),
        min_value: Optional[float] = Query(None, description="Минимальная стоимость портфеля"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получить список всех портфелей пользователя с последними данными.
    """
    return analytics_service.get_accounts_summary(
        db,
        current_user.id,
        include_inactive=include_inactive,
        min_value=min_value
    )


@router.get("/summary", response_model=schemas.OverallSummaryResponse)
def get_summary(
        include_inactive: bool = Query(False, description="Включать закрытые счета"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получить сводную информацию по всем портфелям пользователя.
    """
    return analytics_service.get_overall_summary(
        db,
        current_user.id,
        include_inactive=include_inactive
    )


@router.get("/accounts/{account_id}", response_model=schemas.AccountDetailResponse)
def get_account_detail(
        account_id: int,
        days: int = Query(30, ge=1, le=365, description="Дней истории"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получить детальную информацию по конкретному портфелю.
    """
    detail = analytics_service.get_account_detail(
        db,
        account_id,
        current_user.id,
        days=days
    )
    if not detail:
        raise HTTPException(status_code=404, detail="Account not found")
    return detail


@router.get("/robots/{robot_id}/metrics", response_model=schemas.RobotMetricsResponse)
def get_robot_metrics(
        robot_id: int,
        recent_limit: int = Query(20, ge=1, le=100, description="Последних сделок"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """KPI торгового робота: win rate, PnL, drawdown, profit factor."""
    from app.core.config import settings
    result = analytics_service.get_robot_metrics(
        db,
        robot_id=robot_id,
        recent_limit=recent_limit,
        schema=settings.DB_SCHEMA,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Robot not found or no trades")
    return result


@router.get("/accounts/{account_id}/positions")
def get_account_positions(
        account_id: int,
        snapshot_id: Optional[int] = Query(None, description="ID снимка (по умолчанию — последний)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Получить позиции портфеля из конкретного снимка."""
    positions = analytics_service.get_account_positions(
        db, account_id, current_user.id, snapshot_id=snapshot_id
    )
    return {"positions": positions}


@router.get("/accounts/{account_id}/history")
def get_account_history(
        account_id: int,
        days: int = Query(30, ge=1, le=365),
        interval: Optional[str] = Query(None, regex="^(day|week|month)$"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получить историю снимков портфеля с возможностью агрегации по интервалам.
    """
    # Проверка принадлежности через сервис
    account = analytics_service.check_account_ownership(db, account_id, current_user.id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    history = analytics_service.get_account_history(
        db,
        account_id,
        days=days,
        interval=interval
    )

    return {
        "account_id": account_id,
        "days": days,
        "interval": interval,
        "history": history
    }