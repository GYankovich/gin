from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


class ApiKeyService:
    """Сервис для работы с API ключами"""

    @staticmethod
    def check_existing_token(db: Session, token: str) -> bool:
        """
        Проверяет, существует ли уже активный токен с таким значением
        """
        query = text("""
                     SELECT id FROM ganaly.api_tokens
                     WHERE token = :token AND is_active = 1
                         LIMIT 1
                     """)

        result = db.execute(query, {"token": token}).first()
        return result is not None

    @staticmethod
    def create_key(db: Session, user_id: int, token: str, key_type: str, name: Optional[str] = None) -> dict:
        """
        Создание нового API ключа
        """
        now = datetime.now(timezone.utc)

        try:
            # Проверяем, существует ли уже такой токен у пользователя
            check_token_query = text("""
                                     SELECT id, name, token_type, is_active, created_at
                                     FROM ganaly.api_tokens
                                     WHERE user_id = :user_id
                                       AND token = :token
                                       AND is_active = 1
                                     """)

            existing_token = db.execute(
                check_token_query,
                {
                    "user_id": user_id,
                    "token": token,
                    "key_type": key_type
                }
            ).first()

            if existing_token:
                logger.info(f"Token already exists for user {user_id}")
                raise ValueError("apikey_exists:Токен уже существует")

            # # Проверяем, нет ли уже активного ключа такого типа
            # if key_type == "tinvest":
            #     check_query = text("""
            #                        SELECT id FROM ganaly.api_tokens
            #                        WHERE user_id = :user_id
            #                          AND token_type = :key_type
            #                          AND is_active = 1
            #                        """)
            #
            #     existing_active = db.execute(
            #         check_query,
            #         {"user_id": user_id, "key_type": key_type}
            #     ).first()
            #
            #     if existing_active:
            #         deactivate_query = text("""
            #                                 UPDATE ganaly.api_tokens
            #                                 SET is_active = 0, updated_at = :now
            #                                 WHERE id = :old_id
            #                                 """)
            #         db.execute(deactivate_query, {"old_id": existing_active[0], "now": now})

            # Создаем новый ключ
            insert_query = text("""
                                INSERT INTO ganaly.api_tokens
                                    (user_id, token, token_type, name, is_active, created_at)
                                VALUES
                                    (:user_id, :token, :key_type, :name, 1, :created_at)
                                    RETURNING id, name, token_type, is_active, created_at
                                """)

            result = db.execute(
                insert_query,
                {
                    "user_id": user_id,
                    "token": token,
                    "key_type": key_type,
                    "name": name,
                    "created_at": now
                }
            ).first()

            if not result:
                raise ValueError("create_failed:Не удалось создать ключ")

            db.commit()

            masked_token = token[:6] + "*" * 10 + token[-4:] if len(token) > 20 else "*" * 20

            logger.info(f"Created new {key_type} key for user {user_id} with id {result[0]}")

            return {
                "id": result[0],
                "name": result[1],
                "key_type": result[2],
                "is_active": bool(result[3]),
                "created_at": result[4],
                "masked_token": masked_token
            }
        except ValueError as e:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating API key: {str(e)}")
            raise ValueError(f"create_error:Ошибка при создании ключа: {str(e)}")

    @staticmethod
    def get_user_keys(
            db: Session,
            user_id: int,
            key_type: Optional[str] = None,
            include_inactive: bool = False,
            limit: int = 50,
            offset: int = 0
    ) -> Tuple[List[dict], int]:
        """
        Получение списка ключей пользователя с пагинацией
        """
        # Базовый запрос для подсчета общего количества
        count_query = """
                      SELECT COUNT(*)
                      FROM ganaly.api_tokens
                      WHERE user_id = :user_id \
                      """
        params = {"user_id": user_id}

        if key_type:
            count_query += " AND token_type = :key_type"
            params["key_type"] = key_type

        if not include_inactive:
            count_query += " AND is_active = 1"

        total = db.execute(text(count_query), params).scalar()

        # Запрос для получения данных
        data_query = """
                     SELECT
                         id,
                         name,
                         token_type,
                         is_active,
                         created_at,
                         token
                     FROM ganaly.api_tokens
                     WHERE user_id = :user_id \
                     """

        if key_type:
            data_query += " AND token_type = :key_type"

        if not include_inactive:
            data_query += " AND is_active = 1"

        data_query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

        params.update({"limit": limit, "offset": offset})

        results = db.execute(text(data_query), params).fetchall()

        keys = []
        for row in results:
            token = row[5]
            masked_token = token[:6] + "*" * 10 + token[-4:] if len(token) > 20 else "*" * 20

            keys.append({
                "id": row[0],
                "name": row[1],
                "key_type": row[2],
                "is_active": bool(row[3]),
                "created_at": row[4],
                "masked_token": masked_token
            })

        return keys, total

    @staticmethod
    def get_key_by_id(db: Session, key_id: int, user_id: int) -> Optional[dict]:
        """
        Получение ключа по ID с проверкой принадлежности пользователю
        """
        query = text("""
                     SELECT
                         id,
                         name,
                         token_type,
                         token,
                         is_active,
                         created_at,
                         updated_at,
                         expires_at,
                         last_used_at
                     FROM ganaly.api_tokens
                     WHERE id = :key_id AND user_id = :user_id
                     """)

        result = db.execute(query, {"key_id": key_id, "user_id": user_id}).first()

        if not result:
            return None

        token = result[3]
        masked_token = token[:6] + "*" * 10 + token[-4:] if len(token) > 20 else "*" * 20

        return {
            "id": result[0],
            "name": result[1],
            "key_type": result[2],
            "token": token,
            "is_active": bool(result[4]),
            "created_at": result[5],
            "updated_at": result[6],
            "expires_at": result[7],
            "last_used_at": result[8],
            "masked_token": masked_token
        }

    @staticmethod
    def update_key(
            db: Session,
            key_id: int,
            user_id: int,
            name: Optional[str] = None,
            is_active: Optional[bool] = None
    ) -> Optional[dict]:
        """
        Обновление информации о ключе
        """
        check_query = text("""
                           SELECT id FROM ganaly.api_tokens
                           WHERE id = :key_id AND user_id = :user_id
                           """)

        exists = db.execute(check_query, {"key_id": key_id, "user_id": user_id}).first()

        if not exists:
            return None

        updates = []
        params = {"key_id": key_id, "user_id": user_id, "now": datetime.now(timezone.utc)}

        if name is not None:
            updates.append("name = :name")
            params["name"] = name

        if is_active is not None:
            updates.append("is_active = :is_active")
            params["is_active"] = 1 if is_active else 0

        if not updates:
            return ApiKeyService.get_key_by_id(db, key_id, user_id)

        updates.append("updated_at = :now")
        update_query = f"""
            UPDATE ganaly.api_tokens
            SET {', '.join(updates)}
            WHERE id = :key_id AND user_id = :user_id
            RETURNING id, name, token_type, is_active, created_at, token
        """

        result = db.execute(text(update_query), params).first()

        if not result:
            return None

        token = result[5]
        masked_token = token[:6] + "*" * 10 + token[-4:] if len(token) > 20 else "*" * 20

        return {
            "id": result[0],
            "name": result[1],
            "key_type": result[2],
            "is_active": bool(result[3]),
            "created_at": result[4],
            "masked_token": masked_token
        }

    @staticmethod
    def deactivate_key(db: Session, key_id: int, user_id: int) -> bool:
        """
        Деактивация ключа (мягкое удаление)
        """
        query = text("""
                     UPDATE ganaly.api_tokens
                     SET is_active = 0, updated_at = :now
                     WHERE id = :key_id AND user_id = :user_id AND is_active = 1
                         RETURNING id
                     """)

        result = db.execute(
            query,
            {
                "key_id": key_id,
                "user_id": user_id,
                "now": datetime.now(timezone.utc)
            }
        ).first()

        if result:
            db.commit()
            return True
        return False

    @staticmethod
    def update_last_used(db: Session, key_id: int) -> None:
        """
        Обновление времени последнего использования ключа
        """
        query = text("""
                     UPDATE ganaly.api_tokens
                     SET last_used_at = :now
                     WHERE id = :key_id
                     """)

        db.execute(query, {"key_id": key_id, "now": datetime.now(timezone.utc)})
        db.commit()


# Создаем экземпляр сервиса
api_key_service = ApiKeyService()