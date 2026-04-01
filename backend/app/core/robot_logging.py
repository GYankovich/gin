"""
Единый модуль логирования роботов: БД + файлы.
"""
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import asyncio
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, InterfaceError

from app.core.logging_config import get_robot_logger


class FileLogger:
    """Файловый логгер робота через общий logging_config."""

    def __init__(self, logger_name: str, robot_id: Optional[int] = None):
        self._logger = get_robot_logger(logger_name, robot_id)

    @property
    def logger(self):
        return self._logger


class DatabaseLogger:
    """Логгер записи запусков и API вызовов роботов в БД."""

    def __init__(self, db: Session, schema: str):
        self.db = db
        self.schema = schema

    async def _execute_with_retry(self, query: str, params: Dict[str, Any], fetch_one: bool = False):
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                result = self.db.execute(text(query), params)
                self.db.commit()
                return result.first() if fetch_one else result
            except (OperationalError, InterfaceError) as exc:
                self.db.rollback()
                last_error = exc
                if attempt >= 3:
                    break
                await asyncio.sleep(2 ** (attempt - 1))
            except Exception:
                self.db.rollback()
                raise
        raise last_error

    async def log_api_call_start(
        self,
        robot_name: str,
        robot_version: str,
        endpoint: str,
        request_data: Optional[Dict] = None,
        token_id: Optional[int] = None,
        user_id: Optional[int] = None,
        execution_log_id: Optional[int] = None,
        started_at: Optional[datetime] = None,
    ) -> Optional[int]:
        if started_at is None:
            started_at = datetime.now(timezone.utc)
        query = """
            INSERT INTO {schema}.robot_logs
            (robot_name, robot_version, token_id, user_id, endpoint, request_data, started_at, execution_log_id)
            VALUES
            (:robot_name, :robot_version, :token_id, :user_id, :endpoint, :request_data, :started_at, :execution_log_id)
            RETURNING id
        """.format(schema=self.schema)
        result = await self._execute_with_retry(
            query,
            {
                "robot_name": robot_name,
                "robot_version": robot_version,
                "token_id": token_id,
                "user_id": user_id,
                "endpoint": endpoint,
                "request_data": json.dumps(request_data, ensure_ascii=False, default=str) if request_data else None,
                "started_at": started_at,
                "execution_log_id": execution_log_id,
            },
            fetch_one=True,
        )
        return result[0] if result else None

    async def log_api_call_success(
        self,
        log_id: int,
        response_data: Optional[Dict] = None,
        response_status: Optional[int] = None,
        finished_at: Optional[datetime] = None,
    ) -> bool:
        if finished_at is None:
            finished_at = datetime.now(timezone.utc)
        query = """
            UPDATE {schema}.robot_logs
            SET finished_at = :finished_at,
                duration_ms = EXTRACT(EPOCH FROM (:finished_at - started_at)) * 1000,
                response_data = :response_data,
                response_status = :response_status,
                success = 1
            WHERE id = :log_id
        """.format(schema=self.schema)
        await self._execute_with_retry(
            query,
            {
                "log_id": log_id,
                "finished_at": finished_at,
                "response_data": json.dumps(response_data, ensure_ascii=False, default=str) if response_data else None,
                "response_status": response_status,
            },
        )
        return True

    async def log_api_call_error(
        self,
        log_id: int,
        error_message: str,
        finished_at: Optional[datetime] = None,
    ) -> bool:
        if finished_at is None:
            finished_at = datetime.now(timezone.utc)
        query = """
            UPDATE {schema}.robot_logs
            SET finished_at = :finished_at,
                duration_ms = EXTRACT(EPOCH FROM (:finished_at - started_at)) * 1000,
                error_message = :error_message,
                success = 0
            WHERE id = :log_id
        """.format(schema=self.schema)
        await self._execute_with_retry(
            query,
            {"log_id": log_id, "finished_at": finished_at, "error_message": error_message[:1000]},
        )
        return True


class APILogger:
    """Логгер API вызовов в файл и в таблицу robot_logs."""

    def __init__(
        self,
        db: Session,
        schema: str,
        robot_type: str,
        robot_name: str,
        robot_version: str,
        execution_log_id: int,
        robot_id: Optional[int] = None,
    ):
        self.db = db
        self.schema = schema
        self.robot_type = robot_type
        self.robot_name = robot_name
        self.robot_version = robot_version
        self.execution_log_id = execution_log_id
        self._db_logger = DatabaseLogger(db, schema)
        base_logger_name = "robots.trading" if robot_type == "trading" else "robots.portfolio_updater"
        self._file_logger = FileLogger(base_logger_name, robot_id=robot_id).logger

    async def log(
        self,
        endpoint: str,
        request_data: Optional[Dict] = None,
        response_data: Optional[Dict] = None,
        response_status: Optional[int] = None,
        error_message: Optional[str] = None,
        token_id: Optional[int] = None,
        user_id: Optional[int] = None,
        started_at: Optional[datetime] = None,
    ) -> Optional[int]:
        if started_at is None:
            started_at = datetime.now(timezone.utc)
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        if error_message:
            self._file_logger.error(f"API {endpoint} status=error duration_ms={duration_ms} error={error_message}")
        else:
            self._file_logger.info(f"API {endpoint} status={response_status} duration_ms={duration_ms}")

        log_id = await self._db_logger.log_api_call_start(
            robot_name=f"{self.robot_type}_{self.robot_name}",
            robot_version=self.robot_version,
            endpoint=endpoint,
            request_data=request_data,
            token_id=token_id,
            user_id=user_id,
            execution_log_id=self.execution_log_id,
            started_at=started_at,
        )
        if not log_id:
            return None

        if error_message:
            await self._db_logger.log_api_call_error(log_id=log_id, error_message=error_message, finished_at=finished_at)
        else:
            await self._db_logger.log_api_call_success(
                log_id=log_id,
                response_data=response_data,
                response_status=response_status,
                finished_at=finished_at,
            )
        return log_id
