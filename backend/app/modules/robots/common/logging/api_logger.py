"""
API логгер - объединяет файловое и БД логирование для API вызовов
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsCommonLoggingApiLogger [1]
#/// Исходный модуль `backend/app/modules/robots/common/logging/api_logger.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from .db_logger import DatabaseLogger
from .file_logger import get_file_logger
from app.modules.robots.common.utils import safe_json_dumps


class APILogger:
    """
    Единый логгер для API вызовов роботов

    Использование:
        api_logger = APILogger(db, schema, "portfolio_updater", "main", "1.0.0", execution_id)
        await api_logger.log(
            endpoint="/api/accounts",
            request_data={"account_id": "123"},
            response_data={"status": "ok"},
            token_id=1,
            user_id=5
        )
    """

    def __init__(
            self,
            db: Session,
            schema: str,
            robot_type: str,
            robot_name: str,
            robot_version: str,
            execution_log_id: int
    ):
        """
        Args:
            db: Сессия БД
            schema: Схема БД
            robot_type: Тип робота (portfolio_updater, trading)
            robot_name: Имя робота
            robot_version: Версия робота
            execution_log_id: ID текущего выполнения (из robot_execution_logs)
        """
        self.db = db
        self.schema = schema
        self.robot_type = robot_type
        self.robot_name = robot_name
        self.robot_version = robot_version
        self.execution_log_id = execution_log_id

        self._db_logger = DatabaseLogger(db, schema)
        self._file_logger = get_file_logger(robot_type, robot_name, execution_log_id)

    async def log(
            self,
            endpoint: str,
            request_data: Optional[Dict] = None,
            response_data: Optional[Dict] = None,
            response_status: Optional[int] = None,
            error_message: Optional[str] = None,
            token_id: Optional[int] = None,
            user_id: Optional[int] = None,
            started_at: Optional[datetime] = None
    ) -> Optional[int]:
        """
        Логирует API вызов (файл + БД)

        Returns:
            ID записи в robot_logs или None
        """
        if started_at is None:
            started_at = datetime.now(timezone.utc)

        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        # 1. Файловое логирование
        self._log_to_file(
            endpoint=endpoint,
            request_data=request_data,
            response_data=response_data,
            error_message=error_message,
            duration_ms=duration_ms
        )

        # 2. Логирование в БД
        return await self._log_to_db(
            endpoint=endpoint,
            request_data=request_data,
            response_data=response_data,
            response_status=response_status,
            error_message=error_message,
            token_id=token_id,
            user_id=user_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms
        )

    def _log_to_file(
            self,
            endpoint: str,
            request_data: Optional[Dict],
            response_data: Optional[Dict],
            error_message: Optional[str],
            duration_ms: int
    ):
        """Запись в файловый лог"""
        log_msg = f"📡 API: {endpoint} (duration: {duration_ms}ms)"

        if request_data:
            preview = self._truncate_for_log(request_data)
            log_msg += f"\n   📤 REQUEST: {safe_json_dumps(preview)}"

        if error_message:
            log_msg += f"\n   ❌ ERROR: {error_message[:500]}"
            self._file_logger.error(log_msg)
        else:
            if response_data:
                preview = self._truncate_for_log(response_data)
                log_msg += f"\n   📥 RESPONSE: {safe_json_dumps(preview)}"
            self._file_logger.debug(log_msg)

    async def _log_to_db(
            self,
            endpoint: str,
            request_data: Optional[Dict],
            response_data: Optional[Dict],
            response_status: Optional[int],
            error_message: Optional[str],
            token_id: Optional[int],
            user_id: Optional[int],
            started_at: datetime,
            finished_at: datetime,
            duration_ms: int
    ) -> Optional[int]:
        """Запись в БД"""
        log_id = await self._db_logger.log_api_call_start(
            robot_name=f"{self.robot_type}_{self.robot_name}",
            robot_version=self.robot_version,
            endpoint=endpoint,
            request_data=request_data,
            token_id=token_id,
            user_id=user_id,
            execution_log_id=self.execution_log_id,
            started_at=started_at
        )

        if not log_id:
            return None

        if error_message:
            await self._db_logger.log_api_call_error(
                log_id=log_id,
                error_message=error_message,
                finished_at=finished_at
            )
        else:
            await self._db_logger.log_api_call_success(
                log_id=log_id,
                response_data=response_data,
                response_status=response_status,
                finished_at=finished_at
            )

        return log_id

    @staticmethod
    def _truncate_for_log(data: Optional[Dict], max_len: int = 500) -> Optional[Dict]:
        """Сокращает большие данные для логов"""
        if not data:
            return None

        data_str = safe_json_dumps(data)
        if len(data_str) <= max_len:
            return data

        # Для портфеля оставляем только ключевые поля
        if "positions" in data:
            return {
                "total_amount": data.get("total_amount_portfolio") or data.get("total_amount"),
                "positions_count": len(data.get("positions", [])),
                "truncated": True
            }

        # Для списка счетов
        if "accounts" in data:
            return {
                "accounts_count": len(data.get("accounts", [])),
                "first_account": data.get("accounts", [{}])[0].get("id") if data.get("accounts") else None,
                "truncated": True
            }

        # Для списка позиций
        if isinstance(data, list) and len(data) > 10:
            return {
                "items_count": len(data),
                "first_items": data[:3],
                "truncated": True
            }

        # Иначе возвращаем только ключи
        if isinstance(data, dict):
            return {
                "keys": list(data.keys())[:10],
                "truncated": True
            }

        return {"truncated": True, "original_length": len(data_str)}