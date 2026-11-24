#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesTinvestTokenService [1]
#/// Исходный модуль `backend/app/modules/tinvest/token_service.py` — автоматическая разметка для Obsidian Source Scanner.

# app/modules/tinvest/token_service.py
from typing import Optional, List, Tuple
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.secret_box import open_broker_material, open_secret
from app.modules.tinvest.methods import create_tbank_client
from . import queries, utils

logger = logging.getLogger(__name__)


class TokenService:
    """Сервис для управления API токенами"""

    def __init__(self):
        self.db: Optional[Session] = None

    def _execute(self, query: str, params: dict, fetch_one: bool = False):
        """Утилита для выполнения запросов"""
        result = self.db.execute(text(query), params)
        return result.first() if fetch_one else result

    def _row_to_token_dict(self, row) -> dict:
        """Преобразует строку результата в словарь токена"""
        if not row:
            return {}

        extra = row[10] if len(row) > 10 else None
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except Exception:
                extra = None
        stored_secret = row[11] if len(row) > 11 else None
        token, opened_extra = open_broker_material(
            row[3] if len(row) > 3 else None,
            stored_secret,
            extra if isinstance(extra, dict) else None,
        )
        secret = opened_extra.get("token_secret")
        return {
            "id": utils.safe_int(row[0]),
            "user_id": utils.safe_int(row[1]) if len(row) > 1 else None,
            "token_type": utils.safe_str(row[2]) if len(row) > 2 else "",
            "token": token,
            "token_name": utils.safe_str(row[4], None) if len(row) > 4 else None,
            "status": utils.safe_int(row[5]) if len(row) > 5 and row[5] is not None else 1,
            "created_at": row[6] if len(row) > 6 else None,
            "modification_date": row[7] if len(row) > 7 else None,
            "last_used_at": row[8] if len(row) > 8 else None,
            "expires_at": row[9] if len(row) > 9 else None,
            "extra_data": opened_extra or None,
            "token_secret": secret,
        }

    async def get_user_token(self, db: Session, user_id: int) -> Optional[str]:
        """
        Получение активного токена пользователя (для обратной совместимости)
        """
        self.db = db
        query = queries.build_get_user_token_query()
        result = self._execute(query, {"user_id": user_id}, fetch_one=True)

        if result:
            token = open_secret(utils.safe_str(result[0])) or ""
            token_id = utils.safe_int(result[1])

            return token

        return None

    async def get_active_token(self, db: Session, user_id: int) -> Optional[dict]:
        """Получение активного токена пользователя как dict с id и token."""
        self.db = db
        query = queries.build_get_user_token_query()
        result = self._execute(query, {"user_id": user_id}, fetch_one=True)

        if result:
            token = open_secret(utils.safe_str(result[0])) or ""
            token_id = utils.safe_int(result[1])
            return {"id": token_id, "token": token}

        return None

    async def get_user_tokens(
            self,
            db: Session,
            user_id: int,
            include_inactive: bool = False,
    ) -> List[dict]:
        """
        Получение всех токенов пользователя (по умолчанию только активные).
        """
        self.db = db
        query = queries.build_get_user_tokens_query(active_only=not include_inactive)
        params = {"user_id": user_id}
        results = self._execute(query, params).fetchall()

        tokens = []
        for row in results:
            token_dict = self._row_to_token_dict(row)
            token_dict["token_preview"] = utils.mask_token(token_dict.get("token", ""))
            tokens.append(token_dict)

        return tokens

    async def get_token_by_id(
            self,
            db: Session,
            token_id: int,
            user_id: int
    ) -> Optional[dict]:
        """
        Получение токена по ID (с проверкой принадлежности пользователю)
        """
        self.db = db
        query = queries.build_get_token_by_id_query()
        result = self._execute(
            query,
            {"token_id": token_id, "user_id": user_id},
            fetch_one=True
        )

        if not result:
            return None

        return self._row_to_token_dict(result)

    @staticmethod
    async def test_token(token: str) -> Tuple[bool, str, Optional[List]]:
        """
        Тестирование валидности токена через запрос к API
        """
        try:
            client = create_tbank_client(token)
            accounts = await client.get_accounts()

            if accounts:
                account_types = [acc.get("type", "").replace("ACCOUNT_TYPE_", "") for acc in accounts]
                account_summary = ", ".join(account_types[:3])
                if len(accounts) > 3:
                    account_summary += f" и ещё {len(accounts) - 3}"

                return True, f"Токен валиден. Найдено счетов: {len(accounts)}", accounts
            else:
                return False, "Токен валиден, но счетов не найдено", None

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                return False, "Неверный токен или токен истек", None
            elif "403" in error_msg:
                return False, "Недостаточно прав для доступа к API", None
            elif "429" in error_msg:
                return False, "Слишком много запросов, попробуйте позже", None
            else:
                return False, f"Ошибка проверки токена: {error_msg}", None

    async def update_last_used(self, db: Session, token_id: int):
        """
        Обновление времени последнего использования токена
        """
        self.db = db
        try:
            query = queries.build_update_last_used_query()
            self._execute(
                query,
                {"token_id": token_id, "now": datetime.now(timezone.utc)}
            )
            db.commit()
        except Exception as e:
            logger.error(f"Error updating last_used for token {token_id}: {e}")
            db.rollback()

    async def get_token_stats(self, db: Session, token_id: int, user_id: int) -> Optional[dict]:
        """
        Получение статистики использования токена
        """
        self.db = db

        # Проверяем принадлежность токена
        token = await self.get_token_by_id(db, token_id, user_id)
        if not token:
            return None

        query = queries.build_get_token_stats_query()
        result = self._execute(query, {"token_id": token_id}, fetch_one=True)

        if not result:
            return {
                "total_requests": 0,
                "last_used": token["last_used_at"],
                "accounts_accessed": 0
            }

        return {
            "total_requests": utils.safe_int(result[0]),
            "last_used": result[1] or token["last_used_at"],
            "accounts_accessed": utils.safe_int(result[2])
        }


# Создаем экземпляр сервиса
token_service = TokenService()