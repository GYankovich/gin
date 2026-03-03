"""
Функции для хеширования паролей и работы с JWT токенами
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import logging

from .config import settings
from app.core.database import get_db
from app.modules.auth.models import User

logger = logging.getLogger(__name__)

# Контекст для хеширования паролей (использует bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Схема OAuth2 для получения токена из header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет, совпадает ли пароль с хешем"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Создает хеш пароля"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> Tuple[str, datetime]:
    """
    Создает JWT токен
    """
    to_encode = data.copy()

    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    return encoded_jwt, expire


def decode_token(token: str) -> Optional[dict]:
    """
    Декодирует и проверяет JWT токен

    Возвращает payload или None если токен невалидный
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except jwt.JWTError as e:
        logger.error(f"Token decode error: {str(e)}")
        return None


async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
) -> User:
    """
    Получает текущего пользователя из JWT токена
    """
    if not token:
        logger.error("No token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Декодируем токен
    payload = decode_token(token)
    if not payload:
        logger.error("Invalid token payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Получаем user_id из payload
    user_id = payload.get("sub")
    if not user_id:
        logger.error("No user_id in token payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Ищем пользователя в базе
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User {user_id} not found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    except Exception as e:
        logger.error(f"Database error in get_current_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


async def get_optional_current_user(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Опционально получает текущего пользователя (не требует аутентификации)
    """
    if not token:
        return None

    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None