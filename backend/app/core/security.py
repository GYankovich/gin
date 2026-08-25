"""
Функции для хеширования паролей и работы с JWT токенами
"""
#///EPIC Platform.ITEM Core.TOPIC BackendAppCoreSecurity [1]
#/// Исходный модуль `backend/app/core/security.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import logging
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import settings
from app.core.database import get_db, try_dispose_pool_on_connectivity_error
from app.modules.auth.models import User

logger = logging.getLogger(__name__)

_jwt_ttl_cache_mono: float = 0.0
_jwt_ttl_cache_value: int = 0
_JWT_TTL_CACHE_SECONDS = 60.0

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

    # exp в JWT — вспомогательный; источник истины для сессии — user_token.expires_at в БД.
    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    return encoded_jwt, expire


def decode_token(token: str, verify_exp: bool = False) -> Optional[dict]:
    """
    Декодирует и проверяет JWT токен.

    По умолчанию exp в JWT не проверяется: сессия продлевается в БД (sliding TTL).
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": verify_exp},
        )
        return payload
    except jwt.JWTError as e:
        logger.debug("Token decode error: %s", e)
        return None


def _jwt_ttl_minutes(db: Session) -> int:
    """TTL сессии из app_config; кэш 60с, чтобы polling backtest не бил в БД каждый запрос."""
    global _jwt_ttl_cache_mono, _jwt_ttl_cache_value
    now_mono = time.monotonic()
    if _jwt_ttl_cache_value > 0 and (now_mono - _jwt_ttl_cache_mono) < _JWT_TTL_CACHE_SECONDS:
        return _jwt_ttl_cache_value
    try:
        ttl_raw = db.execute(
            text(f"SELECT value FROM app_config WHERE key = 'jwt_ttl_minutes' LIMIT 1")
        ).scalar()
    except SQLAlchemyError as exc:
        try_dispose_pool_on_connectivity_error(exc)
        if _jwt_ttl_cache_value > 0:
            logger.warning("jwt_ttl_minutes DB read failed, using cached value: %s", exc)
            return _jwt_ttl_cache_value
        raise
    try:
        ttl_minutes = int(ttl_raw) if ttl_raw is not None else int(settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    except (TypeError, ValueError):
        ttl_minutes = int(settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    if ttl_minutes <= 0:
        ttl_minutes = int(settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    _jwt_ttl_cache_mono = now_mono
    _jwt_ttl_cache_value = ttl_minutes
    return ttl_minutes


def resolve_session_user_id(db: Session, token: str, *, slide: bool = False) -> Optional[int]:
    """
    Проверяет сессию по записи user_token (sliding TTL в БД).
    Возвращает user_id или None.
    """
    payload = decode_token(token, verify_exp=False)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    now = datetime.now(timezone.utc)
    try:
        ttl_minutes = _jwt_ttl_minutes(db)

        token_row = db.execute(
            text(
                f"""
                SELECT id, user_id, expires_at
                FROM user_token
                WHERE token = :token AND status = 1
                LIMIT 1
                """
            ),
            {"token": token},
        ).first()
        if not token_row:
            return None

        expires_at = token_row[2]
        if expires_at is None or expires_at <= now:
            db.execute(
                text(
                    f"""
                    UPDATE user_token
                    SET status = 3, invalidated_at = :now
                    WHERE id = :id
                    """
                ),
                {"id": token_row[0], "now": now},
            )
            db.commit()
            return None

        if slide:
            next_expire = now + timedelta(minutes=ttl_minutes)
            db.execute(
                text(f"UPDATE user_token SET expires_at = :exp WHERE id = :id"),
                {"id": token_row[0], "exp": next_expire},
            )
            db.commit()

        try:
            return int(user_id)
        except (TypeError, ValueError):
            return None
    except SQLAlchemyError:
        raise


async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
) -> User:
    """
    Получает текущего пользователя из JWT токена
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info("="*50)
    logger.info("🔐 get_current_user called")
    logger.info(f"Token received: {token[:20] if token else 'None'}...")

    if not token:
        logger.error("❌ No token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = resolve_session_user_id(db, token, slide=True)
    except SQLAlchemyError:
        raise

    if user_id is None:
        logger.error("❌ Invalid or expired session")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info(f"✅ Session valid for user_id={user_id}")

    # Ищем пользователя в базе
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"❌ User {user_id} not found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        logger.info(f"✅ User found: {user.login} (id: {user.id})")
        return user
    except HTTPException:
        raise
    except SQLAlchemyError:
        raise
    except Exception as e:
        logger.error(f"❌ Database error in get_current_user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

def authenticate_ws_user_id(token_str: str) -> Optional[int]:
    """Return user_id from bearer token or None (session checked in DB, not JWT exp)."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return resolve_session_user_id(db, token_str, slide=False)
    finally:
        db.close()


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