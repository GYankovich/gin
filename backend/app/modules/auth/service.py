# app/modules/auth/service.py
"""
Бизнес-логика модуля авторизации с явными SQL запросами
"""
#///EPIC Platform.ITEM Auth.TOPIC Service Layer And Security Flow [1]
#/// Сервис авторизации: валидация пользователя, выпуск JWT, управление профилем
#/// и проверка прав доступа через SQL-слой и security helpers.
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import logging

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

from app.core.security import verify_password, get_password_hash, create_access_token, decode_token
from app.core.config import settings
from . import schemas
from . import queries

logger = logging.getLogger(__name__)


class AuthService:
    """Сервис для работы с авторизацией"""

    def __init__(self):
        self.db: Optional[Session] = None

    def _execute(self, query: str, params: Dict[str, Any], fetch_one: bool = False):
        """Утилита для выполнения запросов"""
        result = self.db.execute(text(query), params)
        return result.first() if fetch_one else result

    @staticmethod
    def _safe_str(value, default: str = '') -> str:
        """Безопасное преобразование в строку"""
        if value is None:
            return default
        return str(value)

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        """Безопасное преобразование в int"""
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_datetime(value, default: Optional[datetime] = None) -> Optional[datetime]:
        """Безопасное преобразование в datetime"""
        return value if value is not None else default

    def _row_to_user_dict(self, row, has_email: bool = True, has_phone: bool = True) -> dict:
        """Преобразует строку результата в словарь пользователя"""
        if not row:
            return {}

        result = {
            "id": self._safe_int(row[0]),
            "login": self._safe_str(row[1]),
            "created_at": self._safe_datetime(row[2]) if len(row) > 2 else None,
        }

        idx = 3
        if has_email:
            result["email"] = self._safe_str(row[idx], None) if idx < len(row) else None
            idx += 1
        if has_phone:
            result["phone"] = self._safe_str(row[idx], None) if idx < len(row) else None

        return result

    @staticmethod
    def to_user_out(user: dict) -> schemas.UserOut:
        return schemas.UserOut(
            id=user["id"],
            login=user["login"],
            email=user.get("email"),
            phone=user.get("phone"),
            created_at=user.get("created_at"),
        )

    def authenticate_user(self, db: Session, login: str, password: str) -> Optional[dict]:
        """
        Проверяет учетные данные пользователя по логину
        Возвращает данные пользователя или None
        """
        self.db = db

        query = queries.build_get_user_by_login_query()
        result = self._execute(query, {"login": login}, fetch_one=True)

        if not result:
            return None

        user_data = {
            "id": result[0],
            "login": result[1],
            "password_hash": result[2],
            "created_at": result[3]
        }

        if not verify_password(password, user_data["password_hash"]):
            return None

        user_full = self.get_user_by_id_full(db, user_data["id"])
        if user_full:
            user_data["email"] = user_full.get("email")
            user_data["phone"] = user_full.get("phone")
            user_data["created_at"] = user_full.get("created_at") or user_data.get("created_at")

        return user_data

    def get_user_by_id_full(self, db: Session, user_id: int) -> Optional[dict]:
        """Получает пользователя с email/phone по ID"""
        self.db = db
        user_query = queries.build_get_user_by_id_query(include_email=True, include_phone=True)
        row = self._execute(user_query, {"user_id": user_id}, fetch_one=True)
        if not row:
            return None
        return self._row_to_user_dict(row, has_email=True, has_phone=True)

    def create_user(self, db: Session, user_data: schemas.UserCreate) -> dict:
        """
        Создает нового пользователя с явными SQL запросами
        """
        self.db = db

        # Проверяем, не занят ли логин
        check_query = queries.build_check_login_exists_query()
        existing = self._execute(check_query, {"login": user_data.login}, fetch_one=True)

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Login already taken"
            )

        # Хешируем пароль
        password_hash = get_password_hash(user_data.password)
        now = datetime.utcnow()

        # Вставляем пользователя
        insert_query = queries.build_create_user_query()
        result = self._execute(
            insert_query,
            {
                "login": user_data.login,
                "password_hash": password_hash,
                "created_at": now
            },
            fetch_one=True
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )

        user_id = result[0]

        # Если указан email, добавляем его
        if user_data.email:
            email_query = queries.build_create_email_query()
            self._execute(
                email_query,
                {
                    "user_id": user_id,
                    "email": user_data.email,
                    "is_primary": True,
                    "valid_from": now
                }
            )

        # Если указан телефон, добавляем его
        if user_data.phone:
            phone_query = queries.build_create_phone_query()
            self._execute(
                phone_query,
                {
                    "user_id": user_id,
                    "phone": user_data.phone,
                    "is_primary": True,
                    "valid_from": now
                }
            )

        db.commit()

        # Возвращаем созданного пользователя
        return {
            "id": user_id,
            "login": user_data.login,
            "email": user_data.email,
            "phone": user_data.phone,
            "created_at": now,
        }

    def create_user_token(self, db: Session, user_data: dict) -> schemas.TokenResponse:
        """
        Создает JWT токен для пользователя и сохраняет его в БД
        """
        self.db = db

        cfg_ttl = db.execute(
            text(f"SELECT value FROM app_config WHERE key = 'jwt_ttl_minutes' LIMIT 1")
        ).scalar()
        try:
            ttl_minutes = int(cfg_ttl) if cfg_ttl is not None else int(settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        except (TypeError, ValueError):
            ttl_minutes = int(settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        if ttl_minutes <= 0:
            ttl_minutes = int(settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        # Создаем JWT токен
        token_data = {"sub": str(user_data["id"]), "login": user_data["login"]}
        token, expires_at = create_access_token(
            token_data,
            timedelta(minutes=ttl_minutes)
        )

        # Текущее время для БД
        now = datetime.now(timezone.utc)

        logger.debug(f"Creating token expires_at: {expires_at}")
        logger.debug(f"Current time: {now}")

        # Сохраняем токен в БД
        token_query = queries.build_create_token_query()
        self._execute(
            token_query,
            {
                "user_id": user_data["id"],
                "token": token,
                "status": 1,  # ACTIVE
                "created_at": now,
                "expires_at": expires_at
            }
        )
        db.commit()

        user_out = self.to_user_out(user_data)

        return schemas.TokenResponse(
            access_token=token,
            expires_at=expires_at,
            user=user_out,
        )

    def get_user_from_token(self, db: Session, token: str) -> Optional[dict]:
        """
        Получает пользователя по токену
        """
        print("="*50)
        print(f"METHOD CALLED: get_user_from_token at {datetime.now()}")
        print(f"Token: {token[:50]}...")
        print("="*50)

        self.db = db

        # Декодируем токен (exp в JWT не проверяем — сессия в user_token)
        payload = decode_token(token, verify_exp=False)
        if not payload:
            logger.warning("Token decode failed")
            return None

        user_id = payload.get("sub")
        if not user_id:
            logger.warning("No user_id in token")
            return None

        try:
            # Проверяем валидность токена в БД
            check_query = queries.build_check_token_valid_query()
            token_check = self._execute(check_query, {"token": token}, fetch_one=True)

            if not token_check or not token_check[2]:  # is_active = False
                logger.warning(f"Token not valid in DB for user {user_id}")
                return None

            # Получаем данные пользователя
            user_query = queries.build_get_user_by_id_query(include_email=True, include_phone=True)
            user = self._execute(user_query, {"user_id": user_id}, fetch_one=True)

            if not user:
                logger.warning(f"User not found: {user_id}")
                return None

            user_dict = self._row_to_user_dict(user, has_email=True, has_phone=True)

            print(f"METHOD FINISHED SUCCESSFULLY for user: {user_dict['login']}")
            logger.info(f"User authenticated: {user_dict['login']}")

            return user_dict

        except Exception as e:
            logger.error(f"Error in get_user_from_token: {e}", exc_info=True)
            print(f"ERROR in method: {e}")
            return None

    def logout_user(self, db: Session, token: str):
        """
        Инвалидирует токен пользователя
        """
        self.db = db

        update_query = queries.build_invalidate_token_query()
        result = self._execute(
            update_query,
            {"token": token, "now": datetime.now(timezone.utc)}
        )
        db.commit()

        logger.info(f"Token invalidated: {token[:20]}...")

    def get_user_contacts(self, db: Session, user_id: int) -> list:
        """
        Получает все контакты пользователя
        """
        self.db = db

        query, params = queries.build_get_user_contacts_query()
        result = self._execute(query, {"user_id": user_id})

        contacts = []
        for row in result:
            contacts.append({
                "type": row[0],
                "value": row[1],
                "is_primary": bool(row[2]),
                "valid_from": row[3],
                "valid_to": row[4]
            })

        return contacts

    def clean_expired_tokens(self, db: Session) -> int:
        """
        Очищает просроченные токены
        Возвращает количество обработанных токенов
        """
        self.db = db

        query = queries.build_clean_expired_tokens_query()
        result = self._execute(query, {})
        db.commit()

        return result.rowcount

    def validate_token(self, db: Session, token: str) -> bool:
        """
        Проверяет, валиден ли токен
        """
        self.db = db

        check_query = queries.build_check_token_valid_query()
        result = self._execute(check_query, {"token": token}, fetch_one=True)

        return bool(result and result[2])  # is_active = True

    def change_user(self, db: Session, user_id: int, data: schemas.UserChange) -> dict:
        """Изменяет логин/контакты и опционально пароль текущего пользователя."""
        self.db = db
        payload = data.model_dump(exclude_unset=True)
        now = datetime.now(timezone.utc)

        new_login = str(payload.get("login") or "").strip()
        if len(new_login) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Логин должен содержать минимум 2 символа",
            )

        taken = self._execute(
            queries.build_check_login_taken_by_other_query(),
            {"login": new_login, "user_id": user_id},
            fetch_one=True,
        )
        if taken:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Login already taken",
            )

        self._execute(
            queries.build_update_login_query(),
            {"user_id": user_id, "login": new_login},
        )

        # Email/phone: only UPDATE existing contact rows (no INSERT).
        email = payload.get("email")
        if email:
            self._execute(
                queries.build_update_user_email_query(),
                {"user_id": user_id, "email": str(email)},
            )
        else:
            self._execute(
                queries.build_expire_user_emails_query(),
                {"user_id": user_id, "now": now},
            )

        phone = payload.get("phone")
        if phone:
            self._execute(
                queries.build_update_user_phone_query(),
                {"user_id": user_id, "phone": str(phone)},
            )
        else:
            self._execute(
                queries.build_expire_user_phones_query(),
                {"user_id": user_id, "now": now},
            )

        if payload.get("new_password"):
            row = self._execute(
                queries.build_get_user_password_hash_query(),
                {"user_id": user_id},
                fetch_one=True,
            )
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

            password_hash = row[2]
            current_password = payload.get("current_password") or ""
            new_password = payload.get("new_password") or ""

            if not verify_password(current_password, password_hash):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Неверный текущий пароль",
                )
            if len(new_password) < 3:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Новый пароль должен содержать минимум 3 символа",
                )
            if current_password == new_password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Новый пароль должен отличаться от текущего",
                )

            self._execute(
                queries.build_update_password_query(),
                {
                    "user_id": user_id,
                    "password_hash": get_password_hash(new_password),
                },
            )
            logger.info("Password changed for user_id=%s", user_id)

        db.commit()
        user = self.get_user_by_id_full(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user


# Создаем глобальный экземпляр сервиса
auth_service = AuthService()