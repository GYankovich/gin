from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

#///EPIC Frontend.ITEM Dashboard.TOPIC Backend Data Endpoint [1]
#/// Компактный endpoint дашборда, собирающий агрегированную витрину данных
#/// для стартового экрана (totals по валютам, assets, accounts).
from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User

from . import schemas
from .service import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.post("/data", response_model=schemas.DashboardDataResponse)
def post_dashboard_data(
    body: schemas.DashboardDataRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Сводка по открытым счетам:
    - totals/assets: только счета без dashboard_hidden;
    - accounts: все OPEN-счета (с флагом dashboard_hidden).
    """
    sort_specs = [(s.column_name, s.sort_type) for s in (body.sort or [])]
    payload = dashboard_service.build_dashboard(db, current_user.id, sort_specs)
    return schemas.DashboardDataResponse(
        totals=payload["totals"],
        assets=payload["assets"],
        accounts=[schemas.DashboardAccountItem(**r) for r in payload["accounts"]],
    )


@router.post("/visibility", response_model=schemas.DashboardVisibilityUpdateResponse)
def post_dashboard_visibility(
    body: schemas.DashboardVisibilityUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Включить/исключить счета из сводки и структуры дашборда."""
    updated = dashboard_service.update_visibility(
        db,
        current_user.id,
        [(item.account_id, item.hidden) for item in (body.accounts or [])],
    )
    return schemas.DashboardVisibilityUpdateResponse(updated=updated)
