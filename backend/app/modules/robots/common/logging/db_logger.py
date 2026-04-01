"""
Логирование в БД для роботов
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import queries


class DatabaseLogger:
    """
    Логгер для записи в БД:
    - robot_execution_logs (запуски роботов)
    - robot_logs (HTTP запросы к API)
    """

    def __init__(self, db: Session, schema: str):
        """
        Args:
            db: Сессия БД
            schema: Схема БД
        """
        self.db = db
        self.schema = schema

    # ============================================================
    # Логирование выполнения роботов
    # ============================================================

    async def create_execution_log(
            self,
            robot_id: int,
            action_type: int = 1,  # 1=start, 2=stop, 3=manual
            status: int = 0,       # 0=pending, 1=success, 2=error
            started_at: Optional[datetime] = None
    ) -> Optional[int]:
        """
        Создаёт запись о запуске робота

        Returns:
            ID созданной записи или None
        """
        if started_at is None:
            started_at = datetime.now(timezone.utc)

        query = queries.build_create_execution_log_query().format(schema=self.schema)

        try:
            result = self.db.execute(
                text(query),
                {
                    "robot_id": robot_id,
                    "action_type": action_type,
                    "status": status,
                    "now": started_at
                }
            ).first()

            self.db.commit()
            return result[0] if result else None

        except Exception as e:
            self.db.rollback()
            raise

    async def complete_execution_log(
            self,
            log_id: int,
            status: int,
            message: Optional[str] = None,
            execution_time_ms: Optional[int] = None,
            error_stack: Optional[str] = None
    ) -> bool:
        """
        Завершает запись выполнения робота

        Args:
            log_id: ID записи из create_execution_log
            status: 1=success, 2=error
            message: Сообщение о результате
            execution_time_ms: Время выполнения в мс
            error_stack: Стек ошибки (при status=2)

        Returns:
            True если успешно
        """
        query = queries.build_update_execution_log_query().format(schema=self.schema)

        try:
            self.db.execute(
                text(query),
                {
                    "log_id": log_id,
                    "status": status,
                    "message": message[:500] if message else None,
                    "execution_time_ms": execution_time_ms,
                    "error_stack": error_stack[:2000] if error_stack else None
                }
            )
            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            return False

    async def get_execution_log(self, log_id: int) -> Optional[Dict]:
        """Получает запись выполнения по ID"""
        query = queries.build_get_execution_log_query().format(schema=self.schema)

        result = self.db.execute(text(query), {"log_id": log_id}).first()

        if not result:
            return None

        return {
            "id": result[0],
            "robot_id": result[1],
            "action_type": result[2],
            "status": result[3],
            "message": result[4],
            "execution_time_ms": result[5],
            "created_at": result[6],
            "error_stack": result[7]
        }

    async def get_last_executions(
            self,
            robot_id: int,
            limit: int = 10
    ) -> list:
        """Получает последние записи выполнения для робота"""
        query = queries.build_get_last_execution_logs_query(limit).format(schema=self.schema)

        results = self.db.execute(
            text(query),
            {"robot_id": robot_id, "limit": limit}
        ).fetchall()

        return [
            {
                "id": row[0],
                "robot_id": row[1],
                "action_type": row[2],
                "status": row[3],
                "message": row[4],
                "execution_time_ms": row[5],
                "created_at": row[6]
            }
            for row in results
        ]

    # ============================================================
    # Логирование API запросов
    # ============================================================

    async def log_api_call_start(
            self,
            robot_name: str,
            robot_version: str,
            endpoint: str,
            request_data: Optional[Dict] = None,
            token_id: Optional[int] = None,
            user_id: Optional[int] = None,
            execution_log_id: Optional[int] = None,
            started_at: Optional[datetime] = None
    ) -> Optional[int]:
        """
        Создаёт запись о начале API запроса

        Returns:
            ID созданной записи
        """
        if started_at is None:
            started_at = datetime.now(timezone.utc)

        query = queries.build_create_api_log_query().format(schema=self.schema)

        try:
            result = self.db.execute(
                text(query),
                {
                    "robot_name": robot_name,
                    "robot_version": robot_version,
                    "token_id": token_id,
                    "user_id": user_id,
                    "endpoint": endpoint,
                    "request_data": self._safe_json_dumps(request_data) if request_data else None,
                    "started_at": started_at,
                    "execution_log_id": execution_log_id
                }
            ).first()

            self.db.commit()
            return result[0] if result else None

        except Exception as e:
            self.db.rollback()
            raise

    async def log_api_call_success(
            self,
            log_id: int,
            response_data: Optional[Dict] = None,
            response_status: Optional[int] = None,
            finished_at: Optional[datetime] = None
    ) -> bool:
        """
        Завершает запись API запроса с успехом
        """
        if finished_at is None:
            finished_at = datetime.now(timezone.utc)

        # Считаем длительность
        log_entry = await self.get_api_log(log_id)
        if log_entry and log_entry.get("started_at"):
            duration_ms = int((finished_at - log_entry["started_at"]).total_seconds() * 1000)
        else:
            duration_ms = 0

        query = queries.build_update_api_log_success_query().format(schema=self.schema)

        try:
            self.db.execute(
                text(query),
                {
                    "log_id": log_id,
                    "finished_at": finished_at,
                    "duration_ms": duration_ms,
                    "response_data": self._safe_json_dumps(response_data) if response_data else None,
                    "response_status": response_status
                }
            )
            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            return False

    async def log_api_call_error(
            self,
            log_id: int,
            error_message: str,
            finished_at: Optional[datetime] = None
    ) -> bool:
        """
        Завершает запись API запроса с ошибкой
        """
        if finished_at is None:
            finished_at = datetime.now(timezone.utc)

        # Считаем длительность
        log_entry = await self.get_api_log(log_id)
        if log_entry and log_entry.get("started_at"):
            duration_ms = int((finished_at - log_entry["started_at"]).total_seconds() * 1000)
        else:
            duration_ms = 0

        query = queries.build_update_api_log_error_query().format(schema=self.schema)

        try:
            self.db.execute(
                text(query),
                {
                    "log_id": log_id,
                    "finished_at": finished_at,
                    "duration_ms": duration_ms,
                    "error_message": error_message[:1000]
                }
            )
            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            return False

    async def get_api_log(self, log_id: int) -> Optional[Dict]:
        """Получает запись API лога по ID"""
        query = """
            SELECT id, robot_name, endpoint, request_data, response_data,
                   started_at, finished_at, duration_ms, success, 
                   response_status, error_message
            FROM {}.robot_logs
            WHERE id = :log_id
        """.format(self.schema)

        result = self.db.execute(text(query), {"log_id": log_id}).first()

        if not result:
            return None

        return {
            "id": result[0],
            "robot_name": result[1],
            "endpoint": result[2],
            "request_data": self._safe_json_loads(result[3]),
            "response_data": self._safe_json_loads(result[4]),
            "started_at": result[5],
            "finished_at": result[6],
            "duration_ms": result[7],
            "success": result[8],
            "response_status": result[9],
            "error_message": result[10]
        }

    # ============================================================
    # Статистика
    # ============================================================

    async def get_execution_stats(
            self,
            robot_id: int,
            since: Optional[datetime] = None
    ) -> Dict:
        """
        Получает статистику выполнения робота

        Args:
            robot_id: ID робота
            since: С какой даты считать (по умолчанию последние 24 часа)
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=1)

        query = queries.build_get_logs_stats_query().format(schema=self.schema)

        result = self.db.execute(
            text(query),
            {"robot_id": robot_id, "since": since}
        ).first()

        if not result or not result[0]:
            return {
                "total_executions": 0,
                "success_count": 0,
                "error_count": 0,
                "avg_duration_ms": 0,
                "last_run": None
            }

        return {
            "total_executions": result[0],
            "success_count": result[1] or 0,
            "error_count": result[2] or 0,
            "avg_duration_ms": round(result[3] or 0, 2),
            "last_run": result[4]
        }

    async def get_api_errors_stats(
            self,
            robot_name: str,
            since: Optional[datetime] = None
    ) -> list:
        """
        Получает статистику по ошибкам API для робота
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=1)

        query = queries.build_get_api_errors_stats_query().format(schema=self.schema)

        results = self.db.execute(
            text(query),
            {"robot_name": robot_name, "since": since}
        ).fetchall()

        return [
            {
                "endpoint": row[0],
                "error_count": row[1],
                "last_error": row[2]
            }
            for row in results
        ]

    # ============================================================
    # Вспомогательные методы
    # ============================================================

    @staticmethod
    def _safe_json_dumps(data: Any) -> Optional[str]:
        """Безопасное преобразование в JSON строку"""
        if data is None:
            return None
        try:
            return json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            return str(data)[:500]

    @staticmethod
    def _safe_json_loads(data: Optional[str]) -> Optional[Any]:
        """Безопасное преобразование JSON строки в объект"""
        if not data:
            return None
        try:
            return json.loads(data)
        except Exception:
            return None


# Импорт для timedelta
from datetime import timedelta
from typing import Any