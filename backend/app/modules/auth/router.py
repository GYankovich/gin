# app/modules/auth/router.py
"""
Маршруты для модуля авторизации
"""
#///EPIC Platform.ITEM Auth.TOPIC REST Authentication Endpoints [1]
#/// Роуты авторизации: login/register/profile и операции валидации токена
#/// для сессионного доступа к защищенным разделам API.
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from typing import Optional

from app.core.database import get_db
from . import schemas, service

router = APIRouter(prefix="/auth", tags=["auth"])

# Схема для получения токена из заголовка Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_token_from_header(authorization: Optional[str] = Depends(oauth2_scheme)) -> str:
    """
    Своя зависимость для получения токена без автоматической валидации
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization


@router.post("/register", response_model=schemas.UserOut)
async def register(
        user_data: schemas.UserCreate,
        db: Session = Depends(get_db)
):
    """
    Регистрация нового пользователя
    """
    try:
        user = service.auth_service.create_user(db, user_data)
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/login", response_model=schemas.TokenResponse)
async def login(
        credentials: schemas.LoginRequest,
        db: Session = Depends(get_db)
):
    """
    Вход в систему
    """
    user = service.auth_service.authenticate_user(
        db,
        credentials.login,
        credentials.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect login or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return service.auth_service.create_user_token(db, user)


@router.get("/me", response_model=schemas.UserOut)
async def get_current_user(
        token: str = Depends(get_token_from_header),
        db: Session = Depends(get_db)
):
    """
    Получение информации о текущем пользователе
    """
    user = service.auth_service.get_user_from_token(db, token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return schemas.UserOut(
        id=user["id"],
        login=user["login"],
        email=user.get("email"),
        phone=user.get("phone")
    )


@router.post("/logout")
async def logout(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
):
    """
    Выход из системы (инвалидация токена)
    """
    service.auth_service.logout_user(db, token)
    return {"message": "Successfully logged out"}


@router.post("/clean-tokens")
async def clean_expired_tokens(
        db: Session = Depends(get_db)
):
    """
    Очистка просроченных токенов (можно вызывать по расписанию)
    """
    count = service.auth_service.clean_expired_tokens(db)
    return {"message": f"Cleaned {count} expired tokens"}


@router.get("/validate-token")
async def validate_token(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
):
    """
    Проверка валидности токена
    """
    is_valid = service.auth_service.validate_token(db, token)
    return {"valid": is_valid}