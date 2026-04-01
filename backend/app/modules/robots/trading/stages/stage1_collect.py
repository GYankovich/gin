"""
Stage 1: Сбор роботов, которые должны быть запущены по расписанию
"""
from datetime import datetime, time
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.modules.robots.trading import queries as trading_queries

logger = get_logger(__name__)


class Stage1Collect:
    """Сбор роботов по расписанию"""

    def __init__(self, db: Session, schema: str, log_func=None):
        self.db = db
        self.schema = schema
        self.log_func = log_func

    def _write_log(self, message: str):
        if self.log_func:
            self.log_func(f"[STAGE1] {message}")
        else:
            logger.info(f"[STAGE1] {message}")

    def _should_run_now(self, robot: Dict) -> bool:
        """Проверяет, должен ли робот запуститься сейчас"""
        from datetime import datetime, time, timezone

        now = datetime.now(timezone.utc)
        current_weekday = now.weekday() + 1

        # Проверка по дням недели
        weekdays = robot.get("weekdays")
        if weekdays:
            if not (weekdays & (1 << (current_weekday - 1))):
                return False

        # Проверка по времени
        start_time = robot.get("start_time")
        end_time = robot.get("end_time")

        if start_time and end_time:
            current_time = now.time()

            # Приводим start_time и end_time к time без tzinfo
            if hasattr(start_time, 'tzinfo') and start_time.tzinfo is not None:
                start_time = start_time.replace(tzinfo=None)
            if hasattr(end_time, 'tzinfo') and end_time.tzinfo is not None:
                end_time = end_time.replace(tzinfo=None)

            # Если это datetime, берем time()
            if isinstance(start_time, datetime):
                start_time = start_time.time()
            if isinstance(end_time, datetime):
                end_time = end_time.time()

            # Если это строка (например "10:00:00+03"), парсим
            if isinstance(start_time, str):
                start_time = time.fromisoformat(start_time[:8])
            if isinstance(end_time, str):
                end_time = time.fromisoformat(end_time[:8])

            if current_time < start_time or current_time > end_time:
                return False

        return True

    async def execute(self) -> List[Dict[str, Any]]:
        """
        Получает список роботов, которые должны быть запущены

        Returns:
            List[Dict]: список роботов с полями:
                - robot_id
                - user_id
                - token_id
                - token
                - config
                - schedule_type
                - interval_seconds
                - start_time
                - end_time
                - weekdays
        """
        self._write_log("=" * 60)
        self._write_log("📋 STAGE 1: Сбор роботов по расписанию")
        self._write_log("=" * 60)

        query = trading_queries.build_collect_scheduled_trading_robots_query().format(schema=self.schema)

        self._write_log(f"📝 SQL запрос:\n{query}")

        try:
            result = self.db.execute(text(query)).fetchall()
            self._write_log(f"✅ Найдено записей в БД: {len(result)}")

            robots = []
            for row in result:
                robot = {
                    "robot_id": row[0],
                    "user_id": row[1],
                    "token_id": row[2],
                    "config": row[3] or {},
                    "token": row[4],
                    "schedule_type": row[5],
                    "interval_seconds": row[6],
                    "start_time": row[7],
                    "end_time": row[8],
                    "weekdays": row[9]
                }

                # Проверяем, должен ли запуститься сейчас
                if self._should_run_now(robot):
                    robots.append(robot)
                    self._write_log(f"   ✅ Робот {robot['robot_id']}: должен запуститься")
                else:
                    self._write_log(f"   ⏭️ Робот {robot['robot_id']}: пропуск (не по расписанию)")

            self._write_log(f"📊 ИТОГО: {len(robots)} роботов готовы к запуску")
            return robots

        except Exception as e:
            self._write_log(f"❌ Ошибка при сборе роботов: {e}")
            import traceback
            self._write_log(traceback.format_exc())
            return []