# app/modules/robots/base/base_robot.py
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union
import logging
import json
import traceback

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.robots.common.logger import get_logger
from app.modules.robots.common.utils import safe_int, safe_str, safe_float, safe_bool
from . import queries


logger = logging.getLogger(__name__)


class BaseRobot(ABC):
    """
    Абстрактный базовый класс для всех роботов

    Использование:
        1. Наследовать класс
        2. Реализовать метод execute()
        3. В execute() использовать self._log_api_call() для HTTP-запросов
        4. При ошибках вызывать self._set_execution_error()
    """

    def __init__(
            self,
            robot_type: str,
            robot_name: str,
            version: str = "1.0.0",
            schema: str = None
    ):
        """
        Args:
            robot_type: Тип робота (portfolio_updater, trading и т.д.)
            robot_name: Имя робота (уникальное в рамках типа)
            version: Версия робота
            schema: Схема БД (по умолчанию из settings)
        """
        self.robot_type = robot_type
        self.robot_name = robot_name
        self.version = version
        self.schema = schema or settings.DB_SCHEMA

        # БД и логгер будут инициализированы при запуске
        self.db: Optional[Session] = None
        self.log = get_logger(robot_type, robot_name)

        # Данные текущего запуска
        self._execution_log_id: Optional[int] = None
        self._started_at: Optional[datetime] = None

    # ============================================================
    # Абстрактные методы
    # ============================================================

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Основной метод выполнения работы робота.
        Должен быть переопределён в наследниках.

        Returns:
            Dict с результатами выполнения
        """
        pass

    # ============================================================
    # Публичные методы
    # ============================================================

    async def run(
            self,
            robot_id: int,
            user_id: int,
            token_id: int,
            token: str,
            **kwargs
    ) -> Dict[str, Any]:
        """
        Запуск робота с полным логированием.

        Args:
            robot_id: ID робота в БД
            user_id: ID пользователя
            token_id: ID токена
            token: Значение токена
            **kwargs: Дополнительные параметры для execute()

        Returns:
            Результат выполнения execute()
        """
        self.db = SessionLocal()
        self._started_at = datetime.now(timezone.utc)

        try:
            self.log.info(f"▶️ Запуск робота v{self.version}")
            self.log.info(f"   Robot ID: {robot_id}, User ID: {user_id}, Token ID: {token_id}")

            # 1. Создаем запись о запуске
            await self._create_execution_log(robot_id)

            # 2. Проверяем, нужно ли запускать (расписание, интервалы)
            should_run, skip_reason = await self._should_run(robot_id)

            if not should_run:
                self.log.info(f"⏭️ Пропуск запуска: {skip_reason}")
                await self._complete_execution_log(
                    status=1,  # success (пропуск - это успех)
                    message=f"Skipped: {skip_reason}"
                )
                return {
                    "status": "skipped",
                    "reason": skip_reason
                }

            # 3. Выполняем основную работу
            result = await self.execute(
                robot_id=robot_id,
                user_id=user_id,
                token_id=token_id,
                token=token,
                **kwargs
            )

            # 4. Обновляем время последнего запуска
            await self._update_last_run(robot_id)

            # 5. Завершаем лог успехом
            execution_time = self._get_execution_time_ms()
            await self._complete_execution_log(
                status=1,  # success
                message=f"Completed successfully",
                execution_time_ms=execution_time
            )

            self.log.info(f"✅ Работа завершена за {execution_time}ms")

            return result

        except Exception as e:
            # Логируем ошибку
            error_msg = str(e)
            error_stack = traceback.format_exc()

            self.log.error(f"❌ Ошибка: {error_msg}")
            self.log.error(error_stack)

            # Завершаем лог с ошибкой
            execution_time = self._get_execution_time_ms()
            await self._complete_execution_log(
                status=2,  # error
                message=f"Error: {error_msg[:500]}",
                execution_time_ms=execution_time,
                error_stack=error_stack[:2000]  # ограничиваем длину
            )

            raise

        finally:
            if self.db:
                self.db.close()
                self.db = None
            self._execution_log_id = None
            self._started_at = None

    # ============================================================
    # Защищенные методы (для использования в наследниках)
    # ============================================================

    async def _should_run(self, robot_id: int) -> tuple[bool, Optional[str]]:
        """
        Проверяет, нужно ли запускать робота (по расписанию).
        Может быть переопределено в наследниках.

        Returns:
            (should_run, reason_if_not)
        """
        # Получаем расписание
        query = queries.build_get_robot_schedule_query().format(schema=self.schema)
        schedule = self.db.execute(
            text(query),
            {"robot_id": robot_id}
        ).first()

        if not schedule:
            return True, None  # Нет расписания - запускаем

        schedule_type = schedule[0]      # 1=interval, 2=time_range, 3=market_hours
        interval_seconds = schedule[1]

        # Интервальный режим
        if schedule_type == 1:
            if not interval_seconds:
                return True, None

            # Получаем время последнего запуска
            query = queries.build_get_robot_info_query().format(schema=self.schema)
            robot_info = self.db.execute(
                text(query),
                {"robot_id": robot_id}
            ).first()

            if not robot_info:
                return True, None

            last_started = robot_info[6]  # last_started

            if not last_started:
                return True, None

            # Проверяем интервал
            now = datetime.now(timezone.utc)
            if last_started.tzinfo is None:
                last_started = last_started.replace(tzinfo=timezone.utc)

            seconds_passed = (now - last_started).total_seconds()

            if seconds_passed >= interval_seconds:
                return True, None
            else:
                return False, f"интервал {interval_seconds}с не достигнут (прошло {seconds_passed:.0f}с)"

        # Для других типов расписания пока запускаем
        return True, None


    async def _log_api_call(
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
        Логирует HTTP запрос/ответ в таблицу robot_logs и файловый лог.
        """
        if not self.db or not self._execution_log_id:
            self.log.warning("Cannot log API call: no DB session or execution context")
            return None

        # Используем переданное время или текущее
        if started_at is None:
            started_at = datetime.now(timezone.utc)

        # ============================================================
        # 1. Файловое логирование (детальное)
        # ============================================================

        # Сокращаем данные для лога (если слишком большие)
        request_preview = request_data
        if request_preview and isinstance(request_preview, dict):
            # Для портфеля сокращаем, оставляем только ключи
            if "accountId" in request_preview and len(str(request_preview)) > 500:
                request_preview = {"accountId": request_preview.get("accountId"), "currency": request_preview.get("currency")}

        response_preview = response_data
        if response_preview and isinstance(response_preview, dict):
            # Для портфеля сокращаем
            if "positions" in response_preview and len(str(response_preview)) > 500:
                response_preview = {
                    "total_amount": response_preview.get("total_amount"),
                    "positions_count": response_preview.get("positions_count", len(response_preview.get("positions", [])))
                }

        # Формируем сообщение для файлового лога
        log_message = f"📡 API: {endpoint}"

        if request_data:
            log_message += f"\n   📤 REQUEST: {self._safe_json_dumps(request_preview)[:1000]}"

        if error_message:
            log_message += f"\n   ❌ ERROR: {error_message[:500]}"
        else:
            if response_status:
                log_message += f"\n   📥 STATUS: {response_status}"
            if response_data:
                log_message += f"\n   📥 RESPONSE: {self._safe_json_dumps(response_preview)[:1000]}"

        # Считаем длительность
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        log_message += f"\n   ⏱️  DURATION: {duration_ms}ms"

        # Пишем в файловый лог
        self.log.debug(log_message)

        # ============================================================
        # 2. Логирование в БД
        # ============================================================

        # Создаем запись
        query = queries.build_create_api_log_query().format(schema=self.schema)
        result = self.db.execute(
            text(query),
            {
                "robot_name": f"{self.robot_type}_{self.robot_name}",
                "robot_version": self.version,
                "token_id": token_id,
                "user_id": user_id,
                "endpoint": endpoint,
                "request_data": self._safe_json_dumps(request_data) if request_data else None,
                "started_at": started_at,
                "execution_log_id": self._execution_log_id
            }
        ).first()

        if not result:
            return None

        log_id = result[0]

        # Обновляем с результатом
        if error_message:
            query = queries.build_update_api_log_error_query().format(schema=self.schema)
            self.db.execute(
                text(query),
                {
                    "log_id": log_id,
                    "finished_at": finished_at,
                    "duration_ms": duration_ms,
                    "error_message": error_message[:1000]
                }
            )
        else:
            query = queries.build_update_api_log_success_query().format(schema=self.schema)
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

        return log_id



    # ============================================================
    # Приватные методы
    # ============================================================

    async def _create_execution_log(self, robot_id: int):
        """Создает запись о запуске робота"""
        query = queries.build_create_execution_log_query().format(schema=self.schema)
        result = self.db.execute(
            text(query),
            {
                "robot_id": robot_id,
                "action_type": 1,  # start
                "status": 0,       # pending
                "now": self._started_at
            }
        ).first()

        if result:
            self._execution_log_id = result[0]
            self.db.commit()
            self.log.info(f"   Execution log ID: {self._execution_log_id}")

    async def _complete_execution_log(
            self,
            status: int,
            message: Optional[str] = None,
            execution_time_ms: Optional[int] = None,
            error_stack: Optional[str] = None
    ):
        """Завершает запись выполнения робота"""
        if not self._execution_log_id:
            return

        query = queries.build_update_execution_log_query().format(schema=self.schema)
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
        self.db.commit()

    async def _update_last_run(self, robot_id: int):
        """Обновляет время последнего запуска робота"""
        query = queries.build_update_robot_last_run_query().format(schema=self.schema)
        self.db.execute(
            text(query),
            {
                "robot_id": robot_id,
                "now": datetime.now(timezone.utc)
            }
        )
        self.db.commit()

    def _get_execution_time_ms(self) -> int:
        """Возвращает время выполнения в миллисекундах"""
        if not self._started_at:
            return 0
        now = datetime.now(timezone.utc)
        return int((now - self._started_at).total_seconds() * 1000)

    # ============================================================
    # Вспомогательные методы (для удобства)
    # ============================================================

    def _safe_int(self, value, default: int = 0) -> int:
        """Безопасное преобразование в int"""
        return safe_int(value, default)

    def _safe_str(self, value, default: str = '') -> str:
        """Безопасное преобразование в строку"""
        return safe_str(value, default)

    def _safe_float(self, value, default: float = 0.0) -> float:
        """Безопасное преобразование в float"""
        return safe_float(value, default)

    def _safe_bool(self, value, default: bool = False) -> bool:
        """Безопасное преобразование в bool"""
        return safe_bool(value, default)

    def _safe_json_dumps(self, data: Any) -> str:
        """Безопасное преобразование в JSON для логов"""
        if data is None:
            return "null"
        try:
            return json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            return str(data)[:500]