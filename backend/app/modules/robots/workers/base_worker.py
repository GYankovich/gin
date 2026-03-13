from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any
import logging
import json

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.robots.models import RobotLog

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """
    Базовый класс для всех роботов
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.db: Optional[Session] = None

    @abstractmethod
    async def work(self, token_id: int, user_id: int, token: str) -> Dict[str, Any]:
        """
        Основная работа робота - должна быть переопределена
        """
        pass

    async def run(self, token_id: int, user_id: int, token: str) -> Dict[str, Any]:
        """
        Запуск робота с логированием
        """
        self.db = SessionLocal()
        started_at = datetime.utcnow()
        log_id = None

        try:
            # Создаем запись в логах
            log_id = await self._create_log(token_id, user_id, started_at)

            logger.info(f"🤖 Robot '{self.name}' started for token {token_id}")

            # Выполняем работу
            result = await self.work(token_id, user_id, token)

            finished_at = datetime.utcnow()
            duration = int((finished_at - started_at).total_seconds() * 1000)

            # Обновляем запись в логах
            await self._update_log_success(log_id, result, finished_at, duration)

            logger.info(f"✅ Robot '{self.name}' completed in {duration}ms")

            return result

        except Exception as e:
            finished_at = datetime.utcnow()
            duration = int((finished_at - started_at).total_seconds() * 1000)

            # Обновляем запись в логах с ошибкой
            if log_id:
                await self._update_log_error(log_id, str(e), finished_at, duration)

            logger.error(f"❌ Robot '{self.name}' failed: {e}")
            raise

        finally:
            if self.db:
                self.db.close()
                self.db = None

    async def _create_log(self, token_id: int, user_id: int, started_at: datetime) -> int:
        """
        Создание записи в логах
        """
        query = text("""
                     INSERT INTO ganaly.robot_logs
                         (robot_name, robot_version, token_id, user_id, started_at, endpoint)
                     VALUES
                         (:robot_name, :robot_version, :token_id, :user_id, :started_at, :endpoint)
                         RETURNING id
                     """)

        result = self.db.execute(
            query,
            {
                "robot_name": self.name,
                "robot_version": self.version,
                "token_id": token_id,
                "user_id": user_id,
                "started_at": started_at,
                "endpoint": f"robot://{self.name}"  # Временное значение
            }
        ).first()

        self.db.commit()
        return result[0]

    async def _update_log_success(
            self,
            log_id: int,
            result: Dict[str, Any],
            finished_at: datetime,
            duration_ms: int
    ):
        """
        Обновление записи в логах при успехе
        """
        query = text("""
                     UPDATE ganaly.robot_logs
                     SET finished_at = :finished_at,
                         duration_ms = :duration_ms,
                         response_data = :response_data,
                         success = 1
                     WHERE id = :log_id
                     """)

        self.db.execute(
            query,
            {
                "log_id": log_id,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "response_data": json.dumps(result) if result else None
            }
        )
        self.db.commit()

    async def _update_log_error(
            self,
            log_id: int,
            error_message: str,
            finished_at: datetime,
            duration_ms: int
    ):
        """
        Обновление записи в логах при ошибке
        """
        query = text("""
                     UPDATE ganaly.robot_logs
                     SET finished_at = :finished_at,
                         duration_ms = :duration_ms,
                         error_message = :error_message,
                         success = 0
                     WHERE id = :log_id
                     """)

        self.db.execute(
            query,
            {
                "log_id": log_id,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "error_message": error_message
            }
        )
        self.db.commit()