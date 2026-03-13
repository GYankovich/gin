from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from . import schemas
from .service import analytics_service

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/accounts", response_model=List[schemas.AccountSummary])
def get_accounts(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получить список всех портфелей пользователя с последними данными.
    """
    return analytics_service.get_accounts_summary(db, current_user.id)


@router.get("/summary", response_model=schemas.OverallSummaryResponse)
def get_summary(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получить сводную информацию по всем портфелям пользователя.
    """
    return analytics_service.get_overall_summary(db, current_user.id)


@router.get("/accounts/{account_id}", response_model=schemas.AccountDetailResponse)
def get_account_detail(
        account_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получить детальную информацию по конкретному портфелю.
    """
    detail = analytics_service.get_account_detail(db, account_id, current_user.id)
    if not detail:
        raise HTTPException(status_code=404, detail="Account not found")
    return detail


@router.get("/accounts/{account_id}/history")
def get_account_history(
        account_id: int,
        days: int = Query(30, ge=1, le=365),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получить историю снимков портфеля.
    """
    # Проверка принадлежности
    account = db.execute(
        text("SELECT id FROM ganaly.portfolio_accounts WHERE id = :id AND user_id = :user_id"),
        {"id": account_id, "user_id": current_user.id}
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    history = analytics_service.get_account_history(db, account_id, days)
    return {"account_id": account_id, "days": days, "history": history}