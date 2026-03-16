# app/modules/robots/base/base_robot.py
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.robots.common.logger import get_logger
from app.modules.robots.queries import (
    build_create_robot_log_query,
    build_update_robot_log_success_query,
    build_update_robot_log_error_query
)

logger = logging.getLogger(__name__)


class BaseRobot(ABC):
    """
    Абстрактный базовый класс для всех роботов
    """

    def __init__(self, robot_type: str, robot_name: str, version: str = "1.0.0"):
        self.robot_type = robot_type
        self.robot_name = robot_name
        self.version = version
        self.db: Optional[Session] = None
        self.log = get_logger(robot_type, robot_name)

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Основной метод выполнения работы робота
        Должен быть переопределён в наследниках
        """
        pass

    def _safe_int(self, value, default: int = 0) -> int:
        """Безопасное преобразование в int"""
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _safe_str(self, value, default: str = '') -> str:
        """Безопасное преобразование в строку"""
        if value is None:
            return default
        return str(value)

    def _safe_float(self, value, default: float = 0.0) -> float:
        """Безопасное преобразование в float"""
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    async def run(self, user_id: int, token_id: int, token: str, **kwargs) -> Dict[str, Any]:
        """
        Запуск робота с логированием в БД
        """
        self.db = SessionLocal()
        started_at = datetime.utcnow()
        log_id = None

        try:
            # Логируем запуск
            self.log.info(f"▶️ Запуск робота v{self.version}")
            self.log.info(f"   User ID: {user_id}, Token ID: {token_id}")

            # Создаём запись в БД
            log_id = await self._create_db_log(user_id, token_id, started_at)
            self.log.info(f"   Запись в БД: ID {log_id}")

            # Выполняем основную работу
            result = await self.execute(
                user_id=user_id,
                token_id=token_id,
                token=token,
                **kwargs
            )

            finished_at = datetime.utcnow()
            duration = int((finished_at - started_at).total_seconds() * 1000)

            # Логируем результат
            self.log.info(f"✅ Работа завершена за {duration}ms")
            if result:
                for key, value in result.items():
                    self.log.info(f"   {key}: {value}")

            # Обновляем запись в БД
            await self._update_db_log_success(log_id, result, finished_at, duration)

            return result

        except Exception as e:
            finished_at = datetime.utcnow()
            duration = int((finished_at - started_at).total_seconds() * 1000)

            self.log.error(f"❌ Ошибка: {str(e)}")
            import traceback
            self.log.error(traceback.format_exc())

            if log_id:
                await self._update_db_log_error(log_id, str(e), finished_at, duration)

            raise

        finally:
            if self.db:
                self.db.close()
                self.db = None

    async def _create_db_log(self, user_id: int, token_id: int, started_at: datetime) -> int:
        """Создание записи в логах БД"""
        query = build_create_robot_log_query()
        result = self.db.execute(
            text(query),
            {
                "robot_name": f"{self.robot_type}_{self.robot_name}",
                "robot_version": self.version,
                "token_id": token_id,
                "user_id": user_id,
                "started_at": started_at,
                "endpoint": f"robot://{self.robot_type}/{self.robot_name}",
                "request_data": None
            }
        ).first()

        self.db.commit()
        return result[0]

    async def _update_db_log_success(
            self,
            log_id: int,
            result: Dict[str, Any],
            finished_at: datetime,
            duration_ms: int
    ):
        """Обновление записи в логах при успехе"""
        import json
        query = build_update_robot_log_success_query()
        self.db.execute(
            text(query),
            {
                "log_id": log_id,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "response_data": json.dumps(result) if result else None
            }
        )
        self.db.commit()

    async def _update_db_log_error(
            self,
            log_id: int,
            error_message: str,
            finished_at: datetime,
            duration_ms: int
    ):
        """Обновление записи в логах при ошибке"""
        query = build_update_robot_log_error_query()
        self.db.execute(
            text(query),
            {
                "log_id": log_id,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "error_message": error_message
            }
        )
        self.db.commit()