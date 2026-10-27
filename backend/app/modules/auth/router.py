# app/modules/auth/router.py
"""
Маршруты для модуля авторизации
"""
#///EPIC Platform.ITEM Auth.TOPIC REST Authentication Endpoints [1]
#/// Роуты авторизации: login/register/profile и операции валидации токена
#/// для сессионного доступа к защищенным разделам API.
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from typing import Optional

from app.core.config import settings
from app.core.database import get_db
from . import schemas, service

router = APIRouter(prefix="/auth", tags=["auth"])


def _public_app_base(request: Request) -> str:
    configured = settings.PUBLIC_APP_URL.strip().rstrip("/")
    if configured:
        return configured
    if not settings.is_production:
        origin = (request.headers.get("origin") or "").strip().rstrip("/")
        if origin.startswith("http://") or origin.startswith("https://"):
            return origin
    return "https://ginity.ru"
users_router = APIRouter(prefix="/users", tags=["users"])

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


registration_router = APIRouter(prefix="/registration", tags=["auth"])
change_pass_router = APIRouter(tags=["auth"])


@router.post("", response_model=schemas.RegisterPendingResponse)
async def auth(
        credentials: schemas.LoginRequest,
        db: Session = Depends(get_db),
):
    """Верная связка логин/почта и пароль. Токен — только после /auth/confirm."""
    return service.auth_service.start_email_login(db, credentials)


@router.post("/confirm", response_model=schemas.TokenResponse)
async def auth_confirm(
        payload: schemas.ConfirmRegisterRequest,
        db: Session = Depends(get_db),
):
    """Код из письма совпал — выдаём сессию."""
    return service.auth_service.confirm_email_login(db, payload)


@router.post("/resend", response_model=schemas.RegisterPendingResponse)
async def auth_resend(
        payload: schemas.ResendRegisterRequest,
        db: Session = Depends(get_db),
):
    """Повтор кода входа. Не чаще раза в минуту."""
    return service.auth_service.resend_login_code(db, payload)


@registration_router.post("", response_model=schemas.RegisterPendingResponse)
async def registration(
        user_data: schemas.RegisterRequest,
        db: Session = Depends(get_db),
):
    """Логин и почта свободны, пароль подходит. Аккаунт появится после /registration/confirm."""
    try:
        return service.auth_service.register_with_email(db, user_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}",
        )


@registration_router.post("/confirm", response_model=schemas.TokenResponse)
async def registration_confirm(
        payload: schemas.ConfirmRegisterRequest,
        db: Session = Depends(get_db),
):
    """Код из письма совпал — создаём аккаунт и выдаём сессию."""
    return service.auth_service.confirm_registration(db, payload)


@registration_router.post("/resend", response_model=schemas.RegisterPendingResponse)
async def registration_resend(
        payload: schemas.ResendRegisterRequest,
        db: Session = Depends(get_db),
):
    """Повтор кода регистрации. Не чаще раза в минуту."""
    return service.auth_service.resend_registration_code(db, payload)


@change_pass_router.post("/change_pass_request", response_model=schemas.PasswordForgotResponse)
async def change_pass_request(
        payload: schemas.PasswordForgotRequest,
        request: Request,
        db: Session = Depends(get_db),
):
    """Письмо со ссылкой на почту этого логина. Ответ один и тот же, даже если аккаунта нет."""
    return service.auth_service.request_password_reset(db, payload, _public_app_base(request))


@change_pass_router.get("/change_pass", response_model=schemas.PasswordResetPreview)
async def change_pass_preview(
        token: str,
        db: Session = Depends(get_db),
):
    """Логин и почта из ссылки. Поля только для показа."""
    return service.auth_service.preview_password_reset(db, token)


@change_pass_router.post("/change_pass")
async def change_pass(
        payload: schemas.PasswordResetConfirm,
        db: Session = Depends(get_db),
):
    """Новый пароль по ссылке из письма, без кода на почту."""
    service.auth_service.reset_password(db, payload)
    return {"status": "ok"}


@router.post("/login", response_model=schemas.TokenResponse)
async def login(
        credentials: schemas.LoginRequest,
        db: Session = Depends(get_db)
):
    """
    Прямая сессия для внутренних скриптов. Экран входа ходит в POST /auth и ждёт код.
    """
    user = service.auth_service.authenticate_user(
        db,
        credentials.login,
        credentials.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
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

    return service.auth_service.to_user_out(user)


@users_router.post("/change", response_model=schemas.UserOut)
async def change_user(
        payload: schemas.UserChange,
        token: str = Depends(get_token_from_header),
        db: Session = Depends(get_db),
):
    """Изменение email/телефона и/или пароля текущего пользователя."""
    user = service.auth_service.get_user_from_token(db, token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    updated = service.auth_service.change_user(db, user["id"], payload)
    return service.auth_service.to_user_out(updated)


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