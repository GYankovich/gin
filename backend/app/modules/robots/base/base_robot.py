"""
Абстрактный базовый класс для всех роботов
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import traceback
import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging_config import get_logger
from app.core.robot_logging import APILogger
from . import queries as base_queries

system_log = get_logger("robots.base")


class BaseRobot(ABC):
    """Абстрактный базовый класс для всех роботов"""

    def __init__(
            self,
            robot_type: str,
            robot_name: str,
            version: str = "1.0.0",
            schema: str = None
    ):
        self.robot_type = robot_type
        self.robot_name = robot_name
        self.version = version
        self.schema = schema or settings.DB_SCHEMA

        self.db: Optional[Session] = None
        self._logger = get_logger(f"robots.{robot_type}.{robot_name}")
        self._execution_log_id: Optional[int] = None
        self._started_at: Optional[datetime] = None
        self._api_logger: Optional[APILogger] = None

    @property
    def log(self):
        return self._logger

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        pass

    async def _log_db_operation(self, operation: str, table: str, data: Dict = None, error: str = None):
        """Логирует операцию с БД в файловый лог"""
        log_msg = f"🗄️ DB {operation} on {self.schema}.{table}"
        if data:
            log_msg += f"\n   📦 DATA: {json.dumps(data, ensure_ascii=False, default=str)[:500]}"
        if error:
            log_msg += f"\n   ❌ ERROR: {error}"
        self._logger.debug(log_msg)

    async def _save_execution_log(self, robot_id: int, status: int, message: str = None, execution_time_ms: int = None, error_stack: str = None) -> Optional[int]:
        """Сохраняет запись о выполнении робота в БД"""
        if not self.db:
            self._logger.warning("No DB session, cannot save execution log")
            return None

        try:
            if self._execution_log_id is None:
                query = base_queries.build_create_execution_log_query().format(schema=self.schema)
                result = self.db.execute(
                    text(query),
                    {
                        "robot_id": robot_id,
                        "action_type": 1,
                        "status": 0,
                        "now": self._started_at or datetime.now(timezone.utc)
                    }
                ).first()
                if result:
                    self._execution_log_id = result[0]
                    await self._log_db_operation("INSERT", "robot_execution_logs", {"robot_id": robot_id, "status": 0})
                self.db.commit()
                return self._execution_log_id
            else:
                query = base_queries.build_update_execution_log_query().format(schema=self.schema)
                self.db.execute(
                    text(query),
                    {
                        "log_id": self._execution_log_id,
                        "status": status,
                        "message": message[:500] if message else None,
                        "execution_time_ms": execution_time_ms,
                        "error_stack": error_stack[:2000] if error_stack else None
                    }
                )
                await self._log_db_operation("UPDATE", "robot_execution_logs", {"id": self._execution_log_id, "status": status})
                self.db.commit()
                return self._execution_log_id
        except Exception as e:
            self._logger.error(f"Failed to save execution log: {e}")
            if self.db:
                self.db.rollback()
            return None

    async def run(
            self,
            robot_id: int,
            user_id: int,
            token_id: int,
            token: str,
            **kwargs
    ) -> Dict[str, Any]:
        """Запуск робота с полным логированием"""
        self.db = SessionLocal()
        self._started_at = datetime.now(timezone.utc)

        try:
            self.log.info(f"▶️ Запуск робота v{self.version}")
            self.log.info(f"   Robot ID: {robot_id}, User ID: {user_id}, Token ID: {token_id}")

            # Сохраняем начало выполнения
            await self._save_execution_log(robot_id, 0, "Started")
            if self._execution_log_id:
                self._api_logger = APILogger(
                    db=self.db,
                    schema=self.schema,
                    robot_type=self.robot_type,
                    robot_name=self.robot_name,
                    robot_version=self.version,
                    execution_log_id=self._execution_log_id,
                    robot_id=robot_id
                )

            # Проверяем расписание
            should_run, skip_reason = await self._should_run(robot_id)

            if not should_run:
                self.log.info(f"⏭️ Пропуск запуска: {skip_reason}")
                await self._save_execution_log(robot_id, 1, f"Skipped: {skip_reason}")
                return {"status": "skipped", "reason": skip_reason}

            # Выполняем основную работу
            result = await self.execute(
                robot_id=robot_id,
                user_id=user_id,
                token_id=token_id,
                token=token,
                **kwargs
            )

            # Обновляем время последнего запуска
            await self._update_last_run(robot_id)

            execution_time = self._get_execution_time_ms()
            await self._save_execution_log(robot_id, 1, "Completed successfully", execution_time)
            self.log.info(f"✅ Работа завершена за {execution_time}ms")

            return result

        except Exception as e:
            error_msg = str(e)
            error_stack = traceback.format_exc()

            self.log.error(f"❌ Ошибка: {error_msg}")
            self.log.error(error_stack)

            execution_time = self._get_execution_time_ms()
            await self._save_execution_log(robot_id, 2, f"Error: {error_msg[:500]}", execution_time, error_stack[:2000])

            raise

        finally:
            if self.db:
                self.db.close()
                self.db = None
            self._execution_log_id = None
            self._started_at = None
            self._api_logger = None

    async def log_api_call(
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
        """Логирует API вызов в файл и БД"""
        if not self._api_logger:
            self.log.warning("Cannot log API call: no DB session or execution context")
            return None

        return await self._api_logger.log(
            endpoint=endpoint,
            request_data=request_data,
            response_data=response_data,
            response_status=response_status,
            error_message=error_message,
            token_id=token_id,
            user_id=user_id,
            started_at=started_at
        )

    async def _execute_db_query(
            self,
            query: str,
            params: Dict = None,
            operation_name: str = "EXECUTE"
    ) -> Any:
        """
        Выполняет SQL запрос с логированием

        Args:
            query: SQL запрос
            params: Параметры запроса
            operation_name: Название операции для лога

        Returns:
            Результат выполнения
        """
        start_time = datetime.now(timezone.utc)
        self._logger.debug(f"🗄️ DB {operation_name}: {query[:200]}")
        if params:
            self._logger.debug(f"   PARAMS: {params}")

        try:
            result = self.db.execute(text(query), params or {})

            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            self._logger.debug(f"   DURATION: {duration:.2f}ms")

            return result
        except Exception as e:
            self._logger.error(f"   ❌ DB ERROR: {e}")
            raise

    def _truncate_for_log(self, data: Optional[Dict], max_len: int = 500) -> str:
        """Сокращает большие данные для логов"""
        if not data:
            return "{}"
        import json
        data_str = json.dumps(data, ensure_ascii=False, default=str)
        if len(data_str) <= max_len:
            return data_str
        if "positions" in data:
            return json.dumps({
                "total_amount": data.get("total_amount_portfolio") or data.get("total_amount"),
                "positions_count": len(data.get("positions", [])),
                "truncated": True
            })
        if "accounts" in data:
            return json.dumps({
                "accounts_count": len(data.get("accounts", [])),
                "truncated": True
            })
        return data_str[:max_len] + "... (truncated)"

    async def _should_run(self, robot_id: int) -> tuple[bool, Optional[str]]:
        """Проверяет, нужно ли запускать робота"""
        query = base_queries.build_get_robot_schedule_query().format(schema=self.schema)
        schedule = self.db.execute(text(query), {"robot_id": robot_id}).first()
        if not schedule:
            return True, None

        schedule_type = schedule[0]
        interval_seconds = schedule[1]

        if schedule_type == 1:
            if not interval_seconds:
                return True, None

            query = base_queries.build_get_robot_info_query().format(schema=self.schema)
            robot_info = self.db.execute(text(query), {"robot_id": robot_id}).first()
            if not robot_info:
                return True, None

            last_started = robot_info[6]
            if not last_started:
                return True, None

            now = datetime.now(timezone.utc)
            if last_started.tzinfo is None:
                last_started = last_started.replace(tzinfo=timezone.utc)

            seconds_passed = (now - last_started).total_seconds()
            if seconds_passed >= interval_seconds:
                return True, None
            else:
                return False, f"интервал {interval_seconds}с не достигнут (прошло {seconds_passed:.0f}с)"

        return True, None

    async def _update_last_run(self, robot_id: int):
        """Обновляет время последнего запуска робота"""
        query = base_queries.build_update_robot_last_run_query().format(schema=self.schema)
        self.db.execute(text(query), {"robot_id": robot_id, "now": datetime.now(timezone.utc)})
        await self._log_db_operation("UPDATE", "robots", {"id": robot_id, "last_started": datetime.now(timezone.utc)})
        self.db.commit()

    def _get_execution_time_ms(self) -> int:
        if not self._started_at:
            return 0
        now = datetime.now(timezone.utc)
        return int((now - self._started_at).total_seconds() * 1000)

    def _safe_int(self, value, default: int = 0) -> int:
        from app.modules.robots.common.utils import safe_int
        return safe_int(value, default)

    def _safe_str(self, value, default: str = '') -> str:
        from app.modules.robots.common.utils import safe_str
        return safe_str(value, default)

    def _safe_float(self, value, default: float = 0.0) -> float:
        from app.modules.robots.common.utils import safe_float
        return safe_float(value, default)

    def _safe_bool(self, value, default: bool = False) -> bool:
        from app.modules.robots.common.utils import safe_bool
        return safe_bool(value, default)

    def _safe_json_dumps(self, data: Any) -> str:
        from app.modules.robots.common.utils import safe_json_dumps
        return safe_json_dumps(data)