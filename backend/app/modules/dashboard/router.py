from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

#///EPIC Frontend.ITEM Dashboard.TOPIC Backend Data Endpoint [1]
#/// Компактный endpoint дашборда, собирающий агрегированную витрину данных
#/// для стартового экрана (счета, баланс, изменения, служебные summary).
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
    Сводка по открытым счетам: показатели из всех операций и актуальных снимков в БД, без окна по датам.
    """
    sort_specs = [(s.column_name, s.sort_type) for s in (body.sort or [])]
    rows = dashboard_service.build_dashboard(db, current_user.id, sort_specs)
    return schemas.DashboardDataResponse(
        accounts=[schemas.DashboardAccountItem(**r) for r in rows],
    )
