from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

#///EPIC Platform.ITEM Settings.TOPIC API Keys Endpoints [1]
#/// Управление API-ключами пользователя: создание, обновление, удаление,
#/// активация/деактивация и получение параметров интеграций.
from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from . import schemas, service


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/apikey", tags=["API Keys"])


@router.post("/create", response_model=schemas.ApiKeyResponse)
async def create_api_key(
        key_data: schemas.ApiKeyCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Создание нового API ключа."""
    try:
        key = await service.api_key_service.create_key(
            db=db,
            user_id=current_user.id,
            token=key_data.token,
            key_type=key_data.key_type,
            name=key_data.name,
            refresh_interval_minutes=int(key_data.refresh_interval_minutes or 60),
            extra_data={
                "token_secret": key_data.token_secret,
                "testnet": key_data.testnet,
                "account_type": key_data.account_type,
            },
        )
        return key
    except ValueError as e:
        error_str = str(e)

        if error_str.startswith("apikey_exists"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "apikey_exists",
                    "description": error_str.split(":", 1)[1] if ":" in error_str else "Токен уже существует"
                }
            )
        elif error_str.startswith("create_failed"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "create_failed",
                    "description": error_str.split(":", 1)[1] if ":" in error_str else "Не удалось создать ключ"
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "bad_request",
                    "description": error_str
                }
            )
    except Exception as e:
        logger.error(f"Unexpected error in create_api_key: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "server_error",
                "description": "Внутренняя ошибка сервера"
            }
        )


@router.post("/data", response_model=schemas.ApiKeyListResponse)
async def get_api_keys(
        key_type: Optional[str] = Query(None, description="Фильтр по типу ключа"),
        limit: int = Query(50, ge=1, le=100, description="Количество записей"),
        offset: int = Query(0, ge=0, description="Смещение"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Получение списка API ключей пользователя."""
    keys, total = service.api_key_service.get_user_keys(
        db=db,
        user_id=current_user.id,
        key_type=key_type,
        limit=limit,
        offset=offset
    )

    return schemas.ApiKeyListResponse(
        keys=keys,
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/test", response_model=schemas.ApiKeyTestResponse)
async def test_api_key(
        payload: schemas.ApiKeyTestRequest,
):
    """Проверка валидности ключа без сохранения."""
    result = await service.api_key_service.test_key(
        token=payload.token,
        key_type=payload.key_type,
        token_secret=payload.token_secret,
        testnet=bool(payload.testnet),
        account_type=str(payload.account_type or "UNIFIED"),
    )
    return schemas.ApiKeyTestResponse(**result)


@router.post("/test-stored/{key_id}", response_model=schemas.ApiKeyTestResponse)
async def test_stored_api_key(
        key_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Проверка сохранённого API ключа пользователя."""
    result = await service.api_key_service.test_stored_key(db, key_id, current_user.id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return schemas.ApiKeyTestResponse(**result)


@router.post("/reveal/{key_id}", response_model=schemas.ApiKeyRevealResponse)
async def reveal_api_key(
        key_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Получение полного значения токена (только владелец)."""
    revealed = service.api_key_service.reveal_key_token(db, key_id, current_user.id)
    if revealed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return schemas.ApiKeyRevealResponse(**revealed)


@router.post("/update/{key_id}", response_model=schemas.ApiKeyResponse)
async def update_api_key(
        key_id: int,
        key_data: schemas.ApiKeyUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Обновление названия / статуса / интервала обновления ключа."""
    updated = service.api_key_service.update_key(
        db=db,
        key_id=key_id,
        user_id=current_user.id,
        name=key_data.name,
        status=key_data.status,
        refresh_interval_minutes=key_data.refresh_interval_minutes,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return updated


@router.post("/delete/{key_id}", status_code=status.HTTP_200_OK)
async def delete_api_key(
        key_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Деактивация API ключа."""
    success = service.api_key_service.deactivate_key(db, key_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already inactive"
        )
    return {"message": "API key successfully deleted", "success": True}
