# app/modules/robots/portfolio_updater/robot.py
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy import text

from app.modules.robots.base.base_robot import BaseRobot
from app.modules.tinvest.methods.clients import create_tbank_client
from app.modules.tinvest.service import tinvest_service


class PortfolioUpdaterRobot(BaseRobot):
    """
    Робот для обновления портфеля пользователя
    """

    def __init__(self, robot_name: str = "main"):
        super().__init__(
            robot_type="portfolio_updater",
            robot_name=robot_name,
            version="2.0.0"
        )
        self.schema = "ganaly"  # или берем из настроек

    def _safe_datetime_now(self):
        """Текущее время в UTC"""
        return datetime.now(timezone.utc)

    async def _check_needs_update(self, robot_id: int, token_id: int) -> Tuple[bool, Optional[int], Optional[float]]:
        """
        Проверяет, нужно ли обновлять портфель для робота
        """
        # Получаем расписание робота из robot_schedules
        schedule_query = """
            SELECT schedule_type, interval_seconds, is_active
            FROM {schema}.robot_schedules
            WHERE robot_id = :robot_id AND is_active = 1
            ORDER BY priority DESC, id ASC
            LIMIT 1
        """.format(schema=self.schema)

        schedule = self.db.execute(
            text(schedule_query),
            {"robot_id": robot_id}
        ).first()

        if not schedule:
            self.log.warning(f"Робот {robot_id} не имеет активного расписания")
            return False, None, None

        schedule_type = schedule[0]
        interval_seconds = schedule[1]

        # Получаем последний запуск из robot_execution_logs
        last_run_query = """
            SELECT last_started 
            FROM {schema}.robots
            WHERE id = :robot_id AND status = 1
            LIMIT 1
        """.format(schema=self.schema)

        last_run = self.db.execute(
            text(last_run_query),
            {"robot_id": robot_id}
        ).first()

        # Для interval типа расписания
        if schedule_type == 1:  # INTERVAL
            if not last_run:
                self.log.info(f"Робот {robot_id} никогда не запускался")
                return True, interval_seconds, None

            now = self._safe_datetime_now()
            last_run_at = last_run[0]
            if last_run_at.tzinfo is None:
                last_run_at = last_run_at.replace(tzinfo=timezone.utc)

            seconds_passed = (now - last_run_at).total_seconds()
            needs_update = seconds_passed >= interval_seconds

            self.log.info(
                f"Робот {robot_id}: прошло {seconds_passed:.1f} сек, "
                f"интервал {interval_seconds} сек"
            )

            return needs_update, interval_seconds, seconds_passed

        # Для других типов расписания пока возвращаем True
        return True, None, None

    async def _log_execution(self, robot_id: int, action_type: int, status: int,
                             message: str = None, execution_time_ms: int = None):
        """Логирует выполнение робота"""
        try:
            log_query = """
                INSERT INTO {schema}.robot_execution_logs 
                (robot_id, action_type, status, message, execution_time_ms, created_at)
                VALUES (:robot_id, :action_type, :status, :message, :execution_time_ms, :now)
            """.format(schema=self.schema)

            self.db.execute(
                text(log_query),
                {
                    "robot_id": robot_id,
                    "action_type": action_type,
                    "status": status,
                    "message": message,
                    "execution_time_ms": execution_time_ms,
                    "now": self._safe_datetime_now()
                }
            )
            self.db.commit()
        except Exception as e:
            self.log.error(f"Ошибка при логировании: {e}")

    async def _update_robot_last_run(self, robot_id: int):
        """Обновляет время последнего запуска робота"""
        update_query = """
            UPDATE {schema}.robots
            SET last_started = :now
            WHERE id = :robot_id
        """.format(schema=self.schema)

        self.db.execute(
            text(update_query),
            {
                "robot_id": robot_id,
                "now": self._safe_datetime_now()
            }
        )
        self.db.commit()

    async def _process_account(self, account: dict, token_value: str, user_id: int) -> Tuple[bool, Optional[int]]:
        """Обработка одного счета"""
        try:
            self.log.info(f"  → Счет {account['id']} ({account['name']})")

            portfolio_data = await tinvest_service.get_portfolio_data(token_value, account["id"])

            snapshot_id = await tinvest_service.save_portfolio_snapshot(
                db=self.db,
                user_id=user_id,
                account_id=account["id"],
                account_data=account,
                portfolio_data=portfolio_data
            )

            if snapshot_id:
                self.log.info(f"    ✓ Снимок сохранен (ID: {snapshot_id})")
                return True, snapshot_id
            else:
                self.log.warning(f"    ⚠️ Снимок не сохранен")
                return False, None

        except Exception as e:
            self.log.error(f"    ❌ Ошибка: {e}")
            return False, None

    async def execute(self, robot_id: int, user_id: int, token_id: int,
                      token: str, **kwargs) -> Dict[str, Any]:
        """
        Основная работа робота
        """
        start_time = datetime.now()

        self.log.info(f"🚀 Начало работы для робота {robot_id} (токен {token_id})")

        # Проверяем, нужно ли обновлять
        needs_update, interval_seconds, seconds_passed = await self._check_needs_update(robot_id, token_id)

        if not needs_update:
            self.log.info(f"⏭️ Пропускаем (интервал {interval_seconds} сек не достигнут)")

            # Логируем пропуск
            await self._log_execution(
                robot_id=robot_id,
                action_type=1,  # start
                status=0,  # success
                message=f"Skipped: Интервал {interval_seconds}сек не прошел, прошло {seconds_passed}, признак {needs_update}",
                execution_time_ms=0
            )

            return {
                "status": "skipped",
                "reason": "interval_not_reached",
                "interval_seconds": interval_seconds,
                "minutes_since_last": round(seconds_passed, 1) if seconds_passed else None
            }

        # Создаём клиент T-Invest
        self.log.info("🔌 Подключение к T-Invest API...")
        client = create_tbank_client(token)

        # Получаем счета
        self.log.info("📋 Запрос списка счетов...")
        accounts_raw = await client.get_accounts()

        if not accounts_raw:
            self.log.info("📭 Счетов не найдено")

            # Обновляем время последнего запуска робота
            await self._update_robot_last_run(robot_id)

            # Логируем успешное выполнение
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            await self._log_execution(
                robot_id=robot_id,
                action_type=1,
                status=0,
                message="Completed: no accounts found",
                execution_time_ms=int(execution_time)
            )

            return {
                "status": "success",
                "accounts_found": 0,
                "portfolios_updated": 0,
                "snapshots_saved": 0
            }

        self.log.info(f"📊 Найдено счетов: {len(accounts_raw)}")

        # Преобразуем в нужный формат
        accounts = []
        for acc in accounts_raw:
            accounts.append({
                "id": acc.get("id"),
                "type": self._safe_str(acc.get("type", "")).replace("ACCOUNT_TYPE_", ""),
                "name": self._safe_str(acc.get("name", "")),
                "status": self._safe_str(acc.get("status", "")).replace("ACCOUNT_STATUS_", ""),
                "opened_date": acc.get("openedDate"),
                "closed_date": acc.get("closedDate")
            })

        # Обрабатываем каждый счёт
        portfolios_updated = 0
        snapshots_saved = 0

        for account in accounts:
            success, snapshot_id = await self._process_account(account, token, user_id)
            portfolios_updated += 1
            if snapshot_id:
                snapshots_saved += 1

        # Обновляем время последнего запуска робота
        await self._update_robot_last_run(robot_id)

        # Логируем успешное выполнение
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        await self._log_execution(
            robot_id=robot_id,
            action_type=1,
            status=1,
            message=f"Completed: {snapshots_saved}/{portfolios_updated} snapshots saved",
            execution_time_ms=int(execution_time)
        )

        self.log.info(f"✅ Работа завершена. Обновлено счетов: {portfolios_updated}, снимков: {snapshots_saved}")

        return {
            "status": "success",
            "accounts_found": len(accounts),
            "portfolios_updated": portfolios_updated,
            "snapshots_saved": snapshots_saved,
            "interval_seconds": interval_seconds,
            "execution_time_ms": int(execution_time)
        }