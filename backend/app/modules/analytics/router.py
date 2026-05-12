# app/modules/analytics/router.py
#///EPIC Analytics.ITEM API.TOPIC Portfolio Reporting Endpoints [1]
#/// Роутер аналитики: сводки по счетам, исторические метрики, графики и
#/// агрегаты эффективности портфеля/роботов для UI аналитики.
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from app.modules.tinvest.service import tinvest_service
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
        days: int = Query(30, ge=1, le=3650, description="Дней истории"),
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


@router.get("/robots/trading-overview", response_model=schemas.UserRobotsTradingOverview)
def get_user_robots_trading_overview(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Агрегированные метрики по сделкам всех роботов пользователя."""
    from app.core.config import settings
    return analytics_service.get_user_robots_trading_overview(
        db, user_id=current_user.id, schema=settings.DB_SCHEMA,
    )


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
        user_id=current_user.id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Robot not found")
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
        days: int = Query(30, ge=1, le=3650),
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


@router.post("/snapshots")
def get_snapshots_by_period(
        body: schemas.AnalyticsRangeRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    account = analytics_service.check_account_ownership(db, body.account_id, current_user.id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    history = analytics_service.get_account_history(
        db,
        body.account_id,
        from_date=body.from_date,
        to_date=body.to_date,
    )
    return {
        "account_id": body.account_id,
        "from_date": body.from_date,
        "to_date": body.to_date,
        "history": history,
    }


@router.post("/operations", response_model=schemas.AnalyticsOperationsResponse)
def get_operations_by_period(
        body: schemas.AnalyticsOperationsRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    items = analytics_service.get_account_operations(
        db=db,
        account_id=body.account_id,
        user_id=current_user.id,
        from_date=body.from_date,
        to_date=body.to_date,
        operation_type=body.operation_type,
    )
    return schemas.AnalyticsOperationsResponse(
        account_id=body.account_id,
        from_date=body.from_date,
        to_date=body.to_date,
        total=len(items),
        items=[schemas.AnalyticsOperationsItem(**x) for x in items],
    )


@router.post("/statistics", response_model=schemas.AccountStatisticsResponse)
def get_account_statistics(
        body: schemas.AnalyticsRangeRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    stats = analytics_service.get_account_statistics(
        db=db,
        account_id=body.account_id,
        user_id=current_user.id,
        from_date=body.from_date,
        to_date=body.to_date,
    )
    if not stats:
        raise HTTPException(status_code=404, detail="Account not found")
    return schemas.AccountStatisticsResponse(**stats)


@router.post("/statistics_extended", response_model=schemas.PortfolioStatisticsExtendedResponse)
async def get_account_statistics_extended(
        body: schemas.AnalyticsRangeRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    stats = await analytics_service.get_account_statistics_extended(
        db=db,
        account_id=body.account_id,
        user_id=current_user.id,
        from_date=body.from_date,
        to_date=body.to_date,
    )
    if not stats:
        raise HTTPException(status_code=404, detail="Account not found")
    return schemas.PortfolioStatisticsExtendedResponse(**stats)


@router.post("/chart_series", response_model=schemas.AnalyticsChartSeriesResponse)
def get_account_chart_series(
        body: schemas.AnalyticsChartSeriesRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    result = analytics_service.get_account_chart_series(
        db=db,
        account_id=body.account_id,
        user_id=current_user.id,
        from_date=body.from_date,
        to_date=body.to_date,
        figis=body.figis or [],
    )
    if not result:
        raise HTTPException(status_code=404, detail="Account not found")
    return schemas.AnalyticsChartSeriesResponse(**result)


@router.post("/sync_operations")
async def sync_operations(
        body: schemas.AnalyticsSyncOperationsRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    result = await tinvest_service.sync_account_operations(
        db=db,
        user_id=current_user.id,
        external_account_id=body.account_id,
        from_dt=body.from_date,
        to_dt=body.to_date,
        state=body.state,
        token_id=body.tokenId,
    )
    return {"success": True, "data": result}