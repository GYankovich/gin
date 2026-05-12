# app/modules/apikey/service.py
#///EPIC Platform.ITEM Settings.TOPIC API Key Service Logic [1]
#/// Бизнес-логика API-ключей: SQL-операции CRUD, проверки уникальности/статуса,
#/// аудит изменений и формирование ответов для settings endpoints.
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from . import queries

logger = logging.getLogger(__name__)


class ApiKeyService:
    """Сервис для работы с API ключами"""

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
    def _safe_bool(value, default: bool = False) -> bool:
        """Безопасное преобразование в bool"""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value == 1
        return bool(value)

    @staticmethod
    def _safe_datetime(value, default: Optional[datetime] = None) -> Optional[datetime]:
        """Безопасное преобразование в datetime"""
        return value if value is not None else default

    @staticmethod
    def _mask_token(token: Any) -> str:
        """Маскирует токен для безопасного отображения"""
        if token is None:
            return ""

        if not isinstance(token, str):
            try:
                token = str(token)
            except:
                return "***"

        if len(token) > 20:
            return token[:6] + "*" * 10 + token[-4:]
        return "*" * min(20, len(token))

    def _row_to_api_key_response(self, row, include_token: bool = False) -> dict:
        """Преобразует строку результата в ответ API"""
        if not row:
            return {}

        # Ожидаемая структура row:
        # 0: id
        # 1: name (из api_tokens)
        # 2: token_type
        # 3: is_active
        # 4: created_at
        # 5: token
        # 6: refresh_interval_minutes
        # 7: type_name (из словаря)
        # 8: type_description (из словаря)

        # Формируем объект token_type
        token_type_info = {
            "type": self._safe_int(row[2]) if len(row) > 2 else 0,
            "typeName": self._safe_str(row[7]) if len(row) > 7 and row[7] is not None else "",
            "typeDesc": self._safe_str(row[8]) if len(row) > 8 and row[8] is not None else ""
        }

        result = {
            "id": self._safe_int(row[0]),
            "name": self._safe_str(row[1], None) if len(row) > 1 else None,
            "token_type": token_type_info,  # теперь это объект
            "is_active": self._safe_bool(row[3]) if len(row) > 3 else True,
            "created_at": self._safe_datetime(row[4]) if len(row) > 4 else None,
        }

        # Токен для маскирования (индекс 5)
        token_value = None
        if len(row) > 5:
            token_value = row[5]
            if include_token:
                result["token"] = self._safe_str(token_value) if token_value is not None else None

        # Маскируем токен
        result["masked_token"] = self._mask_token(token_value)

        # Добавляем refresh_interval_minutes (индекс 6)
        if len(row) > 6:
            result["refresh_interval_minutes"] = self._safe_int(row[6], 60)

        return result

    def _row_to_key_detail(self, row) -> dict:
        """Преобразует строку в детальную информацию о ключе"""
        if not row:
            return {}

        token_value = row[3] if len(row) > 3 else None

        result = {
            "id": self._safe_int(row[0]),
            "name": self._safe_str(row[1], None),
            "key_type": self._safe_str(row[2]),
            "token": self._safe_str(token_value) if token_value is not None else None,
            "is_active": self._safe_bool(row[4]) if len(row) > 4 else True,
            "created_at": self._safe_datetime(row[5]) if len(row) > 5 else None,
            "updated_at": self._safe_datetime(row[6]) if len(row) > 6 else None,
            "expires_at": self._safe_datetime(row[7]) if len(row) > 7 else None,
            "last_used_at": self._safe_datetime(row[8]) if len(row) > 8 else None,
        }

        result["masked_token"] = self._mask_token(token_value)
        return result

    def check_existing_token(self, db: Session, token: str) -> bool:
        """
        Проверяет, существует ли уже активный токен с таким значением
        """
        self.db = db
        query = queries.build_check_existing_token_query()
        result = self._execute(query, {"token": token}, fetch_one=True)
        return result is not None

    def create_key(
            self,
            db: Session,
            user_id: int,
            token: str,
            key_type: str,
            name: Optional[str] = None,
            refresh_interval_minutes: int = 60
    ) -> dict:
        """
        Создание нового API ключа
        """
        self.db = db
        now = datetime.now(timezone.utc)

        try:
            # Проверяем, существует ли уже такой токен у пользователя
            check_query = queries.build_check_existing_token_by_user_query()
            existing_token = self._execute(
                check_query,
                {
                    "user_id": user_id,
                    "token": token
                },
                fetch_one=True
            )

            if existing_token:
                logger.info(f"Token already exists for user {user_id}")
                raise ValueError("apikey_exists:Токен уже существует")

            # # Опционально: деактивация старого ключа того же типа
            # if key_type == "tinvest":
            #     check_active_query = queries.build_check_active_key_by_type_query()
            #     existing_active = self._execute(
            #         check_active_query,
            #         {"user_id": user_id, "key_type": key_type},
            #         fetch_one=True
            #     )
            #
            #     if existing_active:
            #         deactivate_query = queries.build_deactivate_old_key_query()
            #         self._execute(
            #             deactivate_query,
            #             {"old_id": existing_active[0], "now": now}
            #         )

            # Создаем новый ключ
            insert_query = queries.build_create_api_key_query()
            result = self._execute(
                insert_query,
                {
                    "user_id": user_id,
                    "token": token,
                    "key_type": key_type,
                    "name": name,
                    "created_at": now,
                    "refresh_interval_minutes": refresh_interval_minutes
                },
                fetch_one=True
            )

            if not result:
                raise ValueError("create_failed:Не удалось создать ключ")

            db.commit()

            logger.info(f"Created new {key_type} key for user {user_id} with id {result[0]}")

            # Преобразуем результат в ответ
            response = self._row_to_api_key_response(result, include_token=False)
            return response

        except ValueError as e:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating API key: {str(e)}")
            raise ValueError(f"create_error:Ошибка при создании ключа: {str(e)}")

    def get_user_keys(
            self,
            db: Session,
            user_id: int,
            key_type: Optional[str] = None,
            limit: int = 50,
            offset: int = 0
    ) -> Tuple[List[dict], int]:
        """
        Получение списка ключей пользователя с пагинацией
        """
        self.db = db

        # Подсчет общего количества
        count_query, count_params = queries.build_count_user_keys_query(
            key_type=key_type
        )

        # Исправляем подстановку параметров
        count_params_fixed = {}
        for k, v in count_params.items():
            if v == ":user_id":
                count_params_fixed["user_id"] = user_id
            else:
                count_params_fixed[k] = v

        total = self._execute(
            count_query,
            count_params_fixed
        ).scalar()

        if total == 0:
            return [], 0

        # Получение данных
        data_query, data_params = queries.build_get_user_keys_query(
            key_type=key_type,
            limit=limit,
            offset=offset
        )

        # Подставляем параметры
        params = {
            "user_id": user_id,
            "limit": limit,
            "offset": offset
        }
        if key_type:
            params["key_type"] = key_type

        results = self._execute(data_query, params).fetchall()

        keys = [self._row_to_api_key_response(row, include_token=False) for row in results]

        return keys, total

    def get_key_by_id(self, db: Session, key_id: int, user_id: int) -> Optional[dict]:
        """
        Получение ключа по ID с проверкой принадлежности пользователю
        """
        self.db = db
        query = queries.build_get_key_by_id_query()
        result = self._execute(
            query,
            {"key_id": key_id, "user_id": user_id},
            fetch_one=True
        )

        if not result:
            return None

        return self._row_to_key_detail(result)

    def update_key(
            self,
            db: Session,
            key_id: int,
            user_id: int,
            name: Optional[str] = None,
            is_active: Optional[bool] = None,
            refresh_interval_minutes: Optional[int] = None
    ) -> Optional[dict]:
        """
        Обновление информации о ключе
        """
        self.db = db

        # Проверяем, что ключ принадлежит пользователю
        check_query = queries.build_check_key_ownership_query()
        exists = self._execute(
            check_query,
            {"key_id": key_id, "user_id": user_id},
            fetch_one=True
        )

        if not exists:
            return None

        # Определяем, какие поля обновляем
        fields_to_update = []
        if name is not None:
            fields_to_update.append("name")
        if is_active is not None:
            fields_to_update.append("is_active")
        if refresh_interval_minutes is not None:
            fields_to_update.append("refresh_interval_minutes")

        if not fields_to_update:
            return self.get_key_by_id(db, key_id, user_id)

        # Строим запрос обновления
        update_query, _ = queries.build_update_key_query(fields_to_update)

        params = {
            "key_id": key_id,
            "user_id": user_id,
            "now": datetime.now(timezone.utc)
        }

        if name is not None:
            params["name"] = name
        if is_active is not None:
            params["is_active"] = 1 if is_active else 0
        if refresh_interval_minutes is not None:
            params["refresh_interval_minutes"] = refresh_interval_minutes

        result = self._execute(update_query, params, fetch_one=True)

        if not result:
            return None

        # Преобразуем результат в ответ
        response = self._row_to_api_key_response(result, include_token=False)
        return response

    def deactivate_key(self, db: Session, key_id: int, user_id: int) -> bool:
        """
        Деактивация ключа (мягкое удаление)
        """
        self.db = db
        query = queries.build_deactivate_key_query()

        result = self._execute(
            query,
            {
                "key_id": key_id,
                "user_id": user_id,
                "now": datetime.now(timezone.utc)
            },
            fetch_one=True
        )

        if result:
            db.commit()
            logger.info(f"Key {key_id} deactivated by user {user_id}")
            return True

        logger.warning(f"Failed to deactivate key {key_id} for user {user_id}")
        return False

    def update_last_used(self, db: Session, key_id: int) -> None:
        """
        Обновление времени последнего использования ключа
        """
        self.db = db
        query = queries.build_update_last_used_query()

        self._execute(
            query,
            {"key_id": key_id, "now": datetime.now(timezone.utc)}
        )
        db.commit()

    def get_token_by_value(self, db: Session, token: str) -> Optional[dict]:
        """
        Получение информации о токене по его значению
        """
        self.db = db
        query = queries.build_get_token_by_value_query()

        result = self._execute(query, {"token": token}, fetch_one=True)

        if not result:
            return None

        return {
            "id": self._safe_int(result[0]),
            "user_id": self._safe_int(result[1]),
            "token_type": self._safe_str(result[2]),
            "name": self._safe_str(result[3], None),
            "is_active": self._safe_bool(result[4]),
            "refresh_interval_minutes": self._safe_int(result[5], 60),
        }

    def get_tokens_by_type(self, db: Session, token_type: str) -> List[dict]:
        """
        Получение всех активных токенов определенного типа
        """
        self.db = db
        query = queries.build_get_tokens_by_type_query()

        results = self._execute(query, {"token_type": token_type}).fetchall()

        tokens = []
        for row in results:
            tokens.append({
                "id": self._safe_int(row[0]),
                "user_id": self._safe_int(row[1]),
                "token": self._safe_str(row[2]),
                "name": self._safe_str(row[3], None),
                "refresh_interval_minutes": self._safe_int(row[4], 60),
                "last_used_at": self._safe_datetime(row[5]),
            })

        return tokens

    def get_expiring_tokens(self, db: Session, days: int = 7) -> List[dict]:
        """
        Получение токенов, срок действия которых истекает
        """
        self.db = db
        query, params = queries.build_get_expiring_tokens_query(days)

        expiry_threshold = datetime.now(timezone.utc).replace(
            hour=23, minute=59, second=59
        ) + timedelta(days=days)

        results = self._execute(
            query,
            {"expiry_threshold": expiry_threshold}
        ).fetchall()

        tokens = []
        for row in results:
            tokens.append({
                "id": self._safe_int(row[0]),
                "user_id": self._safe_int(row[1]),
                "token_type": self._safe_str(row[2]),
                "name": self._safe_str(row[3], None),
                "expires_at": self._safe_datetime(row[4]),
            })

        return tokens

    def bulk_deactivate_tokens(
            self,
            db: Session,
            user_id: int,
            token_type: str
    ) -> int:
        """
        Массовая деактивация токенов пользователя определенного типа
        Возвращает количество деактивированных токенов
        """
        self.db = db
        query = queries.build_bulk_deactivate_tokens_query()

        result = self._execute(
            query,
            {
                "user_id": user_id,
                "token_type": token_type,
                "now": datetime.now(timezone.utc)
            }
        )

        db.commit()
        affected = result.rowcount
        logger.info(f"Deactivated {affected} tokens for user {user_id} of type {token_type}")
        return affected


# Создаем экземпляр сервиса
api_key_service = ApiKeyService()