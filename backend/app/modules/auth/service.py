"""
Бизнес-логика модуля авторизации с явными SQL запросами
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

from app.core.security import verify_password, get_password_hash, create_access_token, decode_token
from app.core.config import settings
from . import schemas

logger = logging.getLogger(__name__)

class AuthService:
    """Сервис для работы с авторизацией"""

    @staticmethod
    def authenticate_user(db: Session, login: str, password: str) -> Optional[dict]:
        """
        Проверяет учетные данные пользователя по логину
        Возвращает данные пользователя или None
        """
        # Явный SQL запрос для получения пользователя
        query = text("""
                     SELECT
                         id,
                         login,
                         password_hash,
                         created_at
                     FROM ganaly.user
                     WHERE login = :login
                     """)

        result = db.execute(query, {"login": login}).first()

        if not result:
            return None

        # Распаковываем результат
        user_data = {
            "id": result[0],
            "login": result[1],
            "password_hash": result[2],
            "created_at": result[3]
        }

        # Проверяем пароль
        if not verify_password(password, user_data["password_hash"]):
            return None

        return user_data

    @staticmethod
    def create_user(db: Session, user_data: schemas.UserCreate) -> dict:
        """
        Создает нового пользователя с явными SQL запросами
        """
        # Проверяем, не занят ли логин
        check_query = text("""
                           SELECT id FROM ganaly.user WHERE login = :login
                           """)

        existing = db.execute(check_query, {"login": user_data.login}).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Login already taken"
            )

        # Хешируем пароль
        password_hash = get_password_hash(user_data.password)

        # Вставляем пользователя
        insert_query = text("""
                            INSERT INTO ganaly.user (login, password_hash, created_at)
                            VALUES (:login, :password_hash, :created_at)
                                RETURNING id, login, created_at
                            """)

        result = db.execute(
            insert_query,
            {
                "login": user_data.login,
                "password_hash": password_hash,
                "created_at": datetime.utcnow()
            }
        ).first()

        user_id = result[0]

        # Если указан email, добавляем его
        if user_data.email:
            email_query = text("""
                               INSERT INTO ganaly.user_email (user_id, email, is_primary, valid_from)
                               VALUES (:user_id, :email, :is_primary, :valid_from)
                               """)
            db.execute(
                email_query,
                {
                    "user_id": user_id,
                    "email": user_data.email,
                    "is_primary": True,
                    "valid_from": datetime.utcnow()
                }
            )

        # Если указан телефон, добавляем его
        if user_data.phone:
            phone_query = text("""
                               INSERT INTO ganaly.user_phone (user_id, phone, is_primary, valid_from)
                               VALUES (:user_id, :phone, :is_primary, :valid_from)
                               """)
            db.execute(
                phone_query,
                {
                    "user_id": user_id,
                    "phone": user_data.phone,
                    "is_primary": True,
                    "valid_from": datetime.utcnow()
                }
            )

        db.commit()

        # Возвращаем созданного пользователя
        return {
            "id": user_id,
            "login": user_data.login,
            "email": user_data.email,
            "phone": user_data.phone
        }

    @staticmethod
    def create_user_token(db: Session, user_data: dict) -> schemas.TokenResponse:
        """
        Создает JWT токен для пользователя и сохраняет его в БД
        """
        # Создаем JWT токен
        token_data = {"sub": str(user_data["id"]), "login": user_data["login"]}
        token, expires_at = create_access_token(
            token_data,
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # СОЗДАЕМ ОСОЗНАННОЕ ВРЕМЯ ДЛЯ БД
        now = datetime.now(timezone.utc)

        logger.debug(f"Creating token expires_at: {expires_at} (type: {type(expires_at)})")
        logger.debug(f"Current time: {now} (type: {type(now)})")

        # Сохраняем токен в БД
        token_query = text("""
                           INSERT INTO ganaly.user_token (user_id, token, status, created_at, expires_at)
                           VALUES (:user_id, :token, :status, :created_at, :expires_at)
                           """)

        db.execute(
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

        return schemas.TokenResponse(
            access_token=token,
            expires_at=expires_at
        )

    @staticmethod
    def get_user_from_token(db: Session, token: str) -> Optional[dict]:
        """
        Получает пользователя по токену - ЗАЩИЩЕННАЯ ВЕРСИЯ
        """
        print("="*50)
        print(f"METHOD CALLED: get_user_from_token at {datetime.now()}")
        print(f"Token: {token[:50]}...")
        print("="*50)

        # Декодируем токен
        payload = decode_token(token)
        if not payload:
            logger.warning("Token decode failed")
            return None

        user_id = payload.get("sub")
        if not user_id:
            logger.warning("No user_id in token")
            return None

        try:
            # Получаем данные пользователя простым запросом
            user_query = text("""
                              SELECT
                                  u.id,
                                  u.login
                              FROM ganaly.user u
                              WHERE u.id = :user_id
                              """)

            user = db.execute(user_query, {"user_id": user_id}).first()

            if not user:
                logger.warning(f"User not found: {user_id}")
                return None

            # Отдельно получаем email
            email_query = text("""
                               SELECT email
                               FROM ganaly.user_email
                               WHERE user_id = :user_id
                                   LIMIT 1
                               """)
            email_result = db.execute(email_query, {"user_id": user_id}).first()

            # Отдельно получаем phone
            phone_query = text("""
                               SELECT phone
                               FROM ganaly.user_phone
                               WHERE user_id = :user_id
                                   LIMIT 1
                               """)
            phone_result = db.execute(phone_query, {"user_id": user_id}).first()

            print(f"METHOD FINISHED SUCCESSFULLY for user: {user[1]}")
            logger.info(f"User authenticated: {user[1]}")

            return {
                "id": user[0],
                "login": user[1],
                "email": email_result[0] if email_result else None,
                "phone": phone_result[0] if phone_result else None
            }

        except Exception as e:
            logger.error(f"Error in get_user_from_token: {e}", exc_info=True)
            print(f"ERROR in method: {e}")
            return None

    @staticmethod
    def logout_user(db: Session, token: str):
        """
        Инвалидирует токен пользователя
        """
        update_query = text("""
                            UPDATE ganaly.user_token
                            SET status = 3, invalidated_at = :now  -- 3 = COMPLETED
                            WHERE token = :token
                            """)

        db.execute(
            update_query,
            {"token": token, "now": datetime.now(timezone.utc)}
        )
        db.commit()


auth_service = AuthService()