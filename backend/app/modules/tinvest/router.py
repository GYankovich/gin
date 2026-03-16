# app/modules/tinvest/router.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

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
        snapshots = await tinvest_service.get_last_snapshots(db, account_id, limit)
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


# ========== ТОКЕНЫ ==========

@router.get("/tokens", response_model=schemas.TokenListResponse)
async def get_tokens(
        include_inactive: bool = Query(False, description="Включать неактивные токены"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение списка токенов пользователя
    """
    try:
        tokens = await token_service.get_user_tokens(db, current_user.id, include_inactive)

        # Преобразуем в response с маскированными токенами
        items = []
        for token in tokens:
            items.append(schemas.TokenResponse(
                id=token["id"],
                token_type=token["token_type"],
                token_name=token["token_name"],
                is_active=token["is_active"],
                created_at=token["created_at"],
                last_used_at=token["last_used_at"],
                expires_at=token["expires_at"],
                token_preview=token.get("token_preview", "***")
            ))

        return schemas.TokenListResponse(
            total=len(items),
            items=items
        )

    except Exception as e:
        logger.error(f"Error getting tokens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении токенов"
        )


@router.get("/tokens/{token_id}", response_model=schemas.TokenResponse)
async def get_token(
        token_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение информации о конкретном токене
    """
    try:
        token = await token_service.get_token_by_id(db, token_id, current_user.id)

        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Токен не найден"
            )

        return schemas.TokenResponse(
            id=token["id"],
            token_type=token["token_type"],
            token_name=token["token_name"],
            is_active=token["is_active"],
            created_at=token["created_at"],
            last_used_at=token["last_used_at"],
            expires_at=token["expires_at"],
            token_preview=token.get("token_preview", "***")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting token {token_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении токена"
        )


@router.post("/tokens", response_model=schemas.TokenResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
        token_data: schemas.TokenCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Создание нового токена T-Invest
    """
    try:
        token = await token_service.create_token(db, current_user.id, token_data)

        return schemas.TokenResponse(
            id=token["id"],
            token_type=token["token_type"],
            token_name=token["token_name"],
            is_active=token["is_active"],
            created_at=token["created_at"],
            last_used_at=token["last_used_at"],
            expires_at=token["expires_at"],
            token_preview=token["token_preview"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании токена: {str(e)}"
        )


@router.patch("/tokens/{token_id}", response_model=schemas.TokenResponse)
async def update_token(
        token_id: int,
        token_data: schemas.TokenUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Обновление информации о токене
    """
    try:
        token = await token_service.update_token(db, token_id, current_user.id, token_data)

        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Токен не найден"
            )

        return schemas.TokenResponse(
            id=token["id"],
            token_type=token["token_type"],
            token_name=token["token_name"],
            is_active=token["is_active"],
            created_at=token["created_at"],
            last_used_at=token["last_used_at"],
            expires_at=token["expires_at"],
            token_preview=token["token_preview"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating token {token_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при обновлении токена"
        )


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(
        token_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Удаление токена
    """
    try:
        deleted = await token_service.delete_token(db, token_id, current_user.id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Токен не найден"
            )

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting token {token_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при удалении токена"
        )


@router.post("/tokens/test", response_model=schemas.TokenTestResponse)
async def test_token(
        test_data: schemas.TokenTestRequest
):
    """
    Тестирование валидности токена без сохранения
    """
    try:
        is_valid, message, accounts = await token_service.test_token(test_data.token)

        return schemas.TokenTestResponse(
            is_valid=is_valid,
            message=message,
            accounts_count=len(accounts) if accounts else 0,
            first_account=accounts[0].get("id") if accounts else None
        )

    except Exception as e:
        logger.error(f"Error testing token: {e}")
        return schemas.TokenTestResponse(
            is_valid=False,
            message=f"Ошибка при тестировании: {str(e)}"
        )


@router.get("/tokens/{token_id}/stats")
async def get_token_stats(
        token_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение статистики использования токена
    """
    try:
        stats = await token_service.get_token_stats(db, token_id, current_user.id)

        if not stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Токен не найден"
            )

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting token stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении статистики"
        )