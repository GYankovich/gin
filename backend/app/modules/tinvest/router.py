# app/modules/tinvest/router.py
#///EPIC Integrations.ITEM TInvest.TOPIC Portfolio Token API [1]
#/// Роутер интеграции T-Invest: портфель/счета/операции и управление токенами доступа,
#/// включая тестирование и синхронизацию данных в локальную БД.
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging
from datetime import datetime, timezone, timedelta

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from .service import tinvest_service
from .token_service import token_service
from . import schemas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


# ========== ПОРТФЕЛЬ ==========

@router.get("/data")
async def get_portfolio(
        account_id: Optional[str] = Query(None, description="ID счета (опционально)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение портфеля пользователя из T-Invest API
    """
    try:
        logger.info(f"Getting portfolio for user {current_user.id}")

        active_token = await token_service.get_active_token(db, current_user.id)
        token = (active_token or {}).get("token")
        token_id = (active_token or {}).get("id")
        if not token:
            logger.warning(f"No T-Invest token found for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "no_token",
                    "message": "Токен T-Invest не найден",
                    "action": "Добавьте токен T-Invest в настройках"
                }
            )

        logger.info(f"Token found for user {current_user.id}, length: {len(token)}")
        portfolio_data = await tinvest_service.get_portfolio_data(
            token,
            account_id,
            db=db,
            token_id=token_id,
            user_id=current_user.id,
            respect_hidden=True,
        )

        logger.info(f"Portfolio data retrieved successfully for user {current_user.id}")
        return portfolio_data

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting portfolio for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "server_error",
                "message": "Ошибка при получении портфеля",
                "error": str(e)
            }
        )


@router.get("/accounts")
async def get_accounts(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение списка счетов пользователя из T-Invest API
    """
    try:
        active_token = await token_service.get_active_token(db, current_user.id)
        token = (active_token or {}).get("token")
        token_id = (active_token or {}).get("id")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Токен T-Invest не найден"
            )

        accounts = await tinvest_service.get_accounts(
            token,
            db=db,
            token_id=token_id,
            user_id=current_user.id,
        )
        hidden = tinvest_service._hidden_external_ids(db, current_user.id)
        return [acc for acc in accounts if str(acc.get("id")) not in hidden]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting accounts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервера"
        )


@router.get("/accounts/db")
async def get_accounts_from_db(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение списка счетов пользователя из БД
    """
    try:
        accounts = await tinvest_service.get_accounts_from_db(db, current_user.id)
        return {
            "total": len(accounts),
            "accounts": accounts
        }
    except Exception as e:
        logger.error(f"Error getting accounts from DB: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении счетов из БД"
        )


@router.post("/refresh-all")
async def refresh_all_portfolios(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение всех счетов и портфелей пользователя с сохранением в БД
    """
    try:
        result = await tinvest_service.refresh_all_portfolios(db, current_user.id)

        return {
            "success": True,
            "message": f"Получено {result['total_accounts']} счетов, сохранено {result['snapshots_saved']} снимков",
            "data": result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing all portfolios: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении: {str(e)}"
        )


@router.post("/operations/sync")
async def sync_account_operations(
        body: schemas.OperationsSyncRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    try:
        result = await tinvest_service.sync_account_operations(
            db=db,
            user_id=current_user.id,
            external_account_id=body.account_id,
            from_dt=body.from_date,
            to_dt=body.to_date,
            state=body.state,
        )
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing account operations: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка синхронизации операций")


@router.get("/operations/{account_id}", response_model=schemas.AccountOperationsResponse)
async def list_account_operations(
        account_id: int,
        from_date: Optional[datetime] = Query(None),
        to_date: Optional[datetime] = Query(None),
        limit: int = Query(500, ge=1, le=5000),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    try:
        now = datetime.now(timezone.utc)
        from_dt = from_date or (now - timedelta(days=90))
        to_dt = to_date or now
        items = await tinvest_service.list_account_operations(
            db=db,
            user_id=current_user.id,
            account_db_id=account_id,
            from_dt=from_dt,
            to_dt=to_dt,
            limit=limit,
        )
        return schemas.AccountOperationsResponse(
            account_id=account_id,
            from_date=from_dt,
            to_date=to_dt,
            total=len(items),
            items=[schemas.AccountOperationItem(**x) for x in items],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing account operations: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка получения операций")


@router.get("/snapshots/{account_id}")
async def get_account_snapshots(
        account_id: int,
        limit: int = Query(10, ge=1, le=100),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение истории снимков портфеля из БД
    """
    try:
        snapshots = await tinvest_service.get_last_snapshots(
            db, account_id, limit, user_id=current_user.id,
        )
        return {
            "account_id": account_id,
            "total": len(snapshots),
            "snapshots": snapshots
        }
    except Exception as e:
        logger.error(f"Error getting snapshots: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении снимков"
        )

# Legacy CRUD /portfolio/tokens удалён — управление ключами только через /api/apikey/*.
