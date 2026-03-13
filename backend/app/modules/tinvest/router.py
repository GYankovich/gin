from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from .service import tinvest_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


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

        token = await tinvest_service.get_user_token(db, current_user.id)
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
        portfolio_data = await tinvest_service.get_portfolio_data(token, account_id)

        logger.info(f"Portfolio data retrieved successfully for user {current_user.id}")
        return portfolio_data

    except HTTPException as he:
        # Пробрасываем HTTP исключения как есть
        raise he
    except Exception as e:
        logger.error(f"Error getting portfolio for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "server_error",
                "message": f"Ошибка при получении портфеля",
                "error": str(e)
            }
        )

@router.get("/accounts")
async def get_accounts(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение списка счетов пользователя
    """
    try:
        token = await tinvest_service.get_user_token(db, current_user.id)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Токен T-Invest не найден"
            )

        accounts = await tinvest_service.get_accounts(token)
        return accounts

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting accounts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервера"
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