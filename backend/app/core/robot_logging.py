"""
Единый модуль логирования роботов: БД + файлы.
"""
#///EPIC Platform.ITEM Core.TOPIC BackendAppCoreRobotLogging [1]
#/// Исходный модуль `backend/app/core/robot_logging.py` — автоматическая разметка для Obsidian Source Scanner.

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
    """Логгер записи запусков и API вызовов роботов в БД (robot_logs — legacy)."""

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
            INSERT INTO robot_logs
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
            UPDATE robot_logs
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
            UPDATE robot_logs
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


def _broker_from_endpoint(endpoint: str, robot_type: str) -> str:
    ep = (endpoint or "").strip().lower()
    if ep.startswith("bybit") or "/v5/" in ep or "api.bybit" in ep:
        return "bybit"
    if ep.startswith("tinvest") or ep.startswith("tinkoff") or "invest.api" in ep:
        return "tinvest"
    if robot_type == "portfolio_updater":
        return "tinvest"
    return "tinvest"


class APILogger:
    """
    Логгер API вызовов:
    - файл робота (полный лог запуска)
    - external_api_logs (все внешние вызовы)
    - robot_logs (legacy, для trading/совместимости)
    """

    def __init__(
        self,
        db: Session,
        schema: str,
        robot_type: str,
        robot_name: str,
        robot_version: str,
        execution_log_id: int,
        robot_id: Optional[int] = None,
        *,
        write_external_api_logs: bool = True,
        write_robot_logs: bool = True,
    ):
        self.db = db
        self.schema = schema
        self.robot_type = robot_type
        self.robot_name = robot_name
        self.robot_version = robot_version
        self.execution_log_id = execution_log_id
        self.robot_id = robot_id
        self.write_external_api_logs = write_external_api_logs
        self.write_robot_logs = write_robot_logs
        self._db_logger = DatabaseLogger(db, schema)
        base_logger_name = "robots.trading" if robot_type == "trading" else "robots.portfolio_updater"
        self._file_logger = FileLogger(base_logger_name, robot_id=robot_id).logger

    async def _write_external_api_log(
        self,
        *,
        endpoint: str,
        request_data: Optional[Dict],
        response_data: Optional[Dict],
        response_status: Optional[int],
        error_message: Optional[str],
        token_id: Optional[int],
        user_id: Optional[int],
        started_at: datetime,
        finished_at: datetime,
    ) -> None:
        duration_ms = int(max(0.0, (finished_at - started_at).total_seconds() * 1000.0))
        broker = _broker_from_endpoint(endpoint, self.robot_type)
        context_ref = str(self.robot_id) if self.robot_id is not None else str(self.execution_log_id)
        query = f"""
            INSERT INTO external_api_logs (
                user_id, token_id, broker, context_type, context_ref,
                endpoint, request_data, response_status, response_data,
                started_at, finished_at, duration_ms, success, error_message
            ) VALUES (
                :user_id, :token_id, :broker, :context_type, :context_ref,
                :endpoint, CAST(:request_data AS jsonb), :response_status, CAST(:response_data AS jsonb),
                :started_at, :finished_at, :duration_ms, :success, :error_message
            )
        """
        try:
            self.db.execute(
                text(query),
                {
                    "user_id": user_id,
                    "token_id": token_id,
                    "broker": broker,
                    "context_type": self.robot_type,
                    "context_ref": context_ref,
                    "endpoint": endpoint,
                    "request_data": json.dumps(request_data or {}, ensure_ascii=False, default=str),
                    "response_status": response_status,
                    "response_data": json.dumps(response_data or {}, ensure_ascii=False, default=str),
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "duration_ms": duration_ms,
                    "success": 0 if error_message else 1,
                    "error_message": (error_message or "")[:2000] or None,
                },
            )
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            self._file_logger.warning("external_api_logs insert failed: %s", exc)

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
            self._file_logger.error(
                "API %s status=error duration_ms=%s error=%s",
                endpoint,
                duration_ms,
                error_message,
            )
        else:
            self._file_logger.info(
                "API %s status=%s duration_ms=%s",
                endpoint,
                response_status,
                duration_ms,
            )

        if self.write_external_api_logs:
            await self._write_external_api_log(
                endpoint=endpoint,
                request_data=request_data,
                response_data=response_data,
                response_status=response_status,
                error_message=error_message,
                token_id=token_id,
                user_id=user_id,
                started_at=started_at,
                finished_at=finished_at,
            )

        if not self.write_robot_logs:
            return None

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
