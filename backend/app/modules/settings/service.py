# app/modules/apikey/service.py
#///EPIC Platform.ITEM Settings.TOPIC API Key Service Logic [1]
#/// Бизнес-логика API-ключей: SQL-операции CRUD, проверки уникальности/статуса,
#/// аудит изменений и формирование ответов для settings endpoints.
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import json

from . import queries
from app.core.secret_box import open_broker_material, open_secret, seal
from app.modules.bybit.http_client import BybitApiError, BybitHttpClient
from app.modules.tinvest.methods import create_tbank_client

logger = logging.getLogger(__name__)

# Акторы аудита — стабильный REST-путь, не login пользователя.
ACTOR_APIKEY_CREATE = "POST /api/apikey/create"
ACTOR_APIKEY_DELETE = "POST /api/apikey/delete"
ACTOR_APIKEY_TEST_STORED = "POST /api/apikey/test-stored"


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

        # id, name, token_type, status, created_at, token, token_secret, extra_data
        # List then adds type_name, type_description, last_used_at, last_error, last_error_at, status_name, status_description.
        is_list_shape = len(row) >= 13

        status_val = self._safe_int(row[3]) if len(row) > 3 else 0
        created_at_val = self._safe_datetime(row[4]) if len(row) > 4 else None

        token_type_info = {
            "type": self._safe_int(row[2]) if len(row) > 2 else 0,
            "typeName": self._safe_str(row[8], "") if is_list_shape and len(row) > 8 and row[8] is not None else "",
            "typeDesc": self._safe_str(row[9], "") if is_list_shape and len(row) > 9 and row[9] is not None else "",
        }
        broker_type = token_type_info["typeName"] or None

        raw_extra = row[7] if len(row) > 7 and isinstance(row[7], dict) else None
        token_value, extra = open_broker_material(
            row[5] if len(row) > 5 else None,
            row[6] if len(row) > 6 else None,
            raw_extra,
        )
        secret = extra.pop("token_secret", None)

        result: dict = {
            "id": self._safe_int(row[0]),
            "name": self._safe_str(row[1], None) if len(row) > 1 else None,
            "token_type": token_type_info,
            "broker_type": broker_type,
            "status": status_val,
            "created_at": created_at_val,
            "masked_token": self._mask_token(token_value),
        }

        if include_token and token_value:
            result["token"] = self._safe_str(token_value)

        if secret:
            result["masked_secret"] = self._mask_token(secret)
            extra["has_token_secret"] = True
        result["extra_data"] = extra or None

        if is_list_shape:
            result["last_used_at"] = self._safe_datetime(row[10])
            result["last_error"] = self._safe_str(row[11], None) if len(row) > 11 else None
            result["last_error_at"] = self._safe_datetime(row[12]) if len(row) > 12 else None
            result["status_name"] = self._safe_str(row[13], None) if len(row) > 13 else None
            result["status_description"] = self._safe_str(row[14], None) if len(row) > 14 else None

            # Небольшой бэкап на случай отсутствия словарных записей.
            if result.get("status") == 3 and not result.get("status_name"):
                result["status_name"] = "Истекший"
            if result.get("status") == 3 and not result.get("status_description"):
                result["status_description"] = "Токен истек"

        return result

    def _row_to_key_detail(self, row) -> dict:
        """Преобразует строку в детальную информацию о ключе"""
        if not row:
            return {}

        raw_extra = row[12] if len(row) > 12 and isinstance(row[12], dict) else None
        token_value, extra = open_broker_material(
            row[3] if len(row) > 3 else None,
            row[4] if len(row) > 4 else None,
            raw_extra,
        )
        secret = extra.pop("token_secret", None)

        result = {
            "id": self._safe_int(row[0]),
            "name": self._safe_str(row[1], None),
            "key_type": self._safe_str(row[2]),
            "token": self._safe_str(token_value) if token_value else None,
            "token_secret": secret or None,
            "status": self._safe_int(row[5]) if len(row) > 5 else 1,
            "created_at": self._safe_datetime(row[6]) if len(row) > 6 else None,
            "modification_date": self._safe_datetime(row[7]) if len(row) > 7 else None,
            "expires_at": self._safe_datetime(row[8]) if len(row) > 8 else None,
            "last_used_at": self._safe_datetime(row[9]) if len(row) > 9 else None,
            "last_error": self._safe_str(row[10], None) if len(row) > 10 else None,
            "last_error_at": self._safe_datetime(row[11]) if len(row) > 11 else None,
            "extra_data": extra or None,
        }

        result["masked_token"] = self._mask_token(token_value)
        return result

    def check_existing_token(self, db: Session, token: str) -> bool:
        """
        Проверяет, существует ли уже активный токен с таким значением
        """
        self.db = db
        query = queries.build_check_existing_token_query()
        rows = self._execute(query, {})
        return any(open_secret(row[0]) == token for row in rows)

    async def create_key(
            self,
            db: Session,
            user_id: int,
            token: str,
            key_type: str,
            name: Optional[str] = None,
            extra_data: Optional[Dict[str, Any]] = None,
            actor: Optional[str] = None,
    ) -> dict:
        """
        Создание нового API ключа
        """
        self.db = db
        now = datetime.now(timezone.utc)
        actor_value = (actor or "").strip() or ACTOR_APIKEY_CREATE

        try:
            # Проверяем, существует ли уже такой токен у пользователя
            check_query = queries.build_check_existing_token_by_user_query()
            existing_rows = self._execute(check_query, {"user_id": user_id})
            if any(open_secret(row[0]) == token for row in existing_rows):
                logger.info(f"Token already exists for user {user_id}")
                raise ValueError("apikey_exists:Токен уже существует")

            extra_payload = dict(extra_data or {})
            secret_plain = extra_payload.pop("token_secret", None) or extra_payload.pop("api_secret", None)
            extra_payload.pop("token_secret", None)
            extra_payload.pop("api_secret", None)
            secret_text = str(secret_plain).strip() if secret_plain else ""

            # Валидация ключа на стороне внешнего API перед сохранением.
            if key_type is not None:
                test = await self.test_key(
                    token=token,
                    key_type=key_type,
                    token_secret=secret_text or None,
                    testnet=False,
                    account_type=str(extra_payload.get("account_type") or "UNIFIED"),
                )
                if not bool(test.get("is_valid")):
                    raise ValueError(f"create_failed:{test.get('message') or 'Ключ не прошел проверку'}")
                if str(key_type).strip().lower() in {"2", "bybit"}:
                    extra_payload["testnet"] = False
            extra_data = extra_payload

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
                    "token": seal(token),
                    "token_secret": seal(secret_text) if secret_text else None,
                    "key_type": key_type,
                    "name": name,
                    "created_at": now,
                    "extra_data": json.dumps(extra_data or {}, ensure_ascii=False),
                    "actor": actor_value,
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
            status: Optional[int] = None,
            actor: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Обновление информации о ключе (внутренний хелпер; публичный REST update отключён).
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
        if status is not None:
            fields_to_update.append("status")

        if not fields_to_update:
            return self.get_key_by_id(db, key_id, user_id)

        # Строим запрос обновления
        update_query, _ = queries.build_update_key_query(fields_to_update)

        params = {
            "key_id": key_id,
            "user_id": user_id,
            "now": datetime.now(timezone.utc),
            "actor": (actor or "").strip() or ACTOR_APIKEY_TEST_STORED,
        }

        if name is not None:
            params["name"] = name
        if status is not None:
            params["status"] = int(status)

        result = self._execute(update_query, params, fetch_one=True)

        if not result:
            return None

        # Преобразуем результат в ответ
        response = self._row_to_api_key_response(result, include_token=False)
        return response

    def deactivate_key(
            self,
            db: Session,
            key_id: int,
            user_id: int,
            actor: Optional[str] = None,
    ) -> bool:
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
                "now": datetime.now(timezone.utc),
                "actor": (actor or "").strip() or ACTOR_APIKEY_DELETE,
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

        rows = self._execute(query, {})
        for result in rows:
            if open_secret(result[5]) != token:
                continue
            return {
                "id": self._safe_int(result[0]),
                "user_id": self._safe_int(result[1]),
                "token_type": self._safe_str(result[2]),
                "name": self._safe_str(result[3], None),
                "status": self._safe_int(result[4]),
            }
        return None

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
                "token": self._safe_str(open_secret(row[2])),
                "name": self._safe_str(row[3], None),
                "last_used_at": self._safe_datetime(row[4]),
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

    async def test_key(
            self,
            *,
            token: str,
            key_type: str,
            token_secret: Optional[str] = None,
            testnet: bool = False,
            account_type: str = "UNIFIED",
            key_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        del account_type
        kt = str(key_type or "").strip().lower()
        if kt in {"tinvest", "1"}:
            try:
                client = create_tbank_client(token, token_id=key_id)
                accounts = await client.get_accounts()
                return {
                    "is_valid": bool(accounts),
                    "message": f"Токен валиден. Счетов: {len(accounts)}" if accounts else "Токен валиден, но счета не найдены",
                    "accounts_count": len(accounts),
                    "first_account": (accounts[0].get("id") if accounts else None),
                }
            except Exception as e:
                return {
                    "is_valid": False,
                    "message": f"T-Invest validation error: {e}",
                    "accounts_count": 0,
                    "first_account": None,
                }

        if kt in {"bybit", "2"}:
            return await self._validate_bybit_credentials(
                token=token,
                token_secret=token_secret,
                testnet=testnet,
                key_id=key_id,
            )

        return {
            "is_valid": False,
            "message": f"Неподдерживаемый тип ключа: {key_type}",
            "accounts_count": 0,
            "first_account": None,
        }

    async def _validate_bybit_credentials(
            self,
            *,
            token: str,
            token_secret: Optional[str],
            testnet: bool = False,
            key_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        del testnet
        if not token_secret:
            return {
                "is_valid": False,
                "message": "Для ByBit проверки требуется API secret",
                "accounts_count": 0,
                "first_account": None,
                "testnet": False,
            }

        client = BybitHttpClient(
            testnet=False,
            api_key=token,
            api_secret=token_secret,
            token_id=key_id,
        )
        try:
            await client.query_api()
            return {
                "is_valid": True,
                "message": "ByBit ключ валиден (mainnet)",
                "accounts_count": 1,
                "first_account": "mainnet",
                "testnet": False,
            }
        except BybitApiError as e:
            return {
                "is_valid": False,
                "message": f"ByBit validation error: {e}. Проверьте API Key/Secret mainnet.",
                "accounts_count": 0,
                "first_account": None,
                "testnet": False,
            }
        finally:
            await client.close()

    async def test_stored_key(self, db: Session, key_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        detail = self.get_key_by_id(db, key_id, user_id)
        if not detail:
            return None
        extra = detail.get("extra_data") if isinstance(detail.get("extra_data"), dict) else {}
        result = await self.test_key(
            token=str(detail.get("token") or ""),
            key_type=str(detail.get("key_type") or ""),
            token_secret=detail.get("token_secret"),
            testnet=False,
            account_type=str(extra.get("account_type") or "UNIFIED"),
            key_id=key_id,
        )
        if result and result.get("is_valid"):
            # Успешная проверка → активный статус (в т.ч. после истечения status=3).
            self.update_key(
                db, key_id, user_id, status=1, actor=ACTOR_APIKEY_TEST_STORED,
            )
            db.commit()
            logger.info("Key %s reactivated (status=1) after successful test for user %s", key_id, user_id)
        return result

    def reveal_key_token(self, db: Session, key_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        detail = self.get_key_by_id(db, key_id, user_id)
        if not detail:
            return None
        token = str(detail.get("token") or "")
        secret = str(detail.get("token_secret") or "").strip()
        out: Dict[str, Any] = {
            "token": token,
            "masked_token": self._mask_token(token),
        }
        if secret:
            out["token_secret"] = secret
            out["masked_secret"] = self._mask_token(secret)
        return out


# Создаем экземпляр сервиса
api_key_service = ApiKeyService()