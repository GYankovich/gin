# app/modules/robots/portfolio_updater/robot.py
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from sqlalchemy import text

from app.modules.robots.base.base_robot import BaseRobot
from app.modules.tinvest.methods.clients import create_tbank_client
from app.modules.tinvest.service import tinvest_service
from app.modules.robots.queries import (
    build_update_token_last_used_query,
    build_get_token_with_refresh_info_query
)


class PortfolioUpdaterRobot(BaseRobot):
    """
    Робот для обновления портфеля пользователя
    """

    def __init__(self, robot_name: str = "main"):
        super().__init__(
            robot_type="portfolio_updater",
            robot_name=robot_name,
            version="1.0.0"
        )

    def _safe_datetime_now(self):
        """Текущее время в UTC"""
        return datetime.now(timezone.utc)

    async def _check_needs_update(self, token_id: int) -> tuple[bool, Optional[int], Optional[float]]:
        """
        Проверяет, нужно ли обновлять портфель для токена
        """
        query = build_get_token_with_refresh_info_query()
        result = self.db.execute(
            text(query),
            {"token_id": token_id}
        ).first()

        if not result:
            self.log.warning(f"Токен {token_id} не найден или неактивен")
            return False, None, None

        refresh_interval = self._safe_int(result[3], 60)
        last_used_at = result[4]

        if last_used_at is None:
            self.log.info(f"Токен {token_id} никогда не использовался")
            return True, refresh_interval, None

        now = self._safe_datetime_now()
        if last_used_at.tzinfo is None:
            last_used_at = last_used_at.replace(tzinfo=timezone.utc)

        minutes_passed = (now - last_used_at).total_seconds() / 60
        needs_update = minutes_passed >= refresh_interval

        self.log.info(f"Токен {token_id}: прошло {minutes_passed:.1f} мин, интервал {refresh_interval} мин")

        return needs_update, refresh_interval, minutes_passed

    async def _update_token_last_used(self, token_id: int):
        """Обновление времени последнего использования токена"""
        query = build_update_token_last_used_query()
        self.db.execute(
            text(query),
            {
                "token_id": token_id,
                "now": self._safe_datetime_now()
            }
        )
        self.db.commit()

    async def _process_account(self, account: dict, token_value: str, user_id: int) -> tuple[bool, Optional[int]]:
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

    async def execute(self, user_id: int, token_id: int, token: str, **kwargs) -> Dict[str, Any]:
        """
        Основная работа робота
        """
        self.log.info(f"🚀 Начало работы для токена {token_id}")

        # Проверяем, нужно ли обновлять
        needs_update, refresh_interval, minutes_passed = await self._check_needs_update(token_id)

        if not needs_update:
            self.log.info(f"⏭️ Пропускаем (интервал {refresh_interval} мин не достигнут)")
            return {
                "status": "skipped",
                "reason": "interval_not_reached",
                "refresh_interval": refresh_interval,
                "minutes_since_last": round(minutes_passed, 1) if minutes_passed else None
            }

        # Создаём клиент T-Invest
        self.log.info("🔌 Подключение к T-Invest API...")
        client = create_tbank_client(token)

        # Получаем счета
        self.log.info("📋 Запрос списка счетов...")
        accounts_raw = await client.get_accounts()

        if not accounts_raw:
            self.log.info("📭 Счетов не найдено")
            await self._update_token_last_used(token_id)
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

        # Обновляем время использования токена
        await self._update_token_last_used(token_id)

        self.log.info(f"✅ Работа завершена. Обновлено счетов: {portfolios_updated}, снимков: {snapshots_saved}")

        return {
            "status": "success",
            "accounts_found": len(accounts),
            "portfolios_updated": portfolios_updated,
            "snapshots_saved": snapshots_saved,
            "refresh_interval_minutes": refresh_interval
        }