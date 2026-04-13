"""
Робот для обновления портфеля пользователя
"""
from typing import Dict, Any, List
from datetime import datetime, timezone
import json

from app.modules.robots.base.base_robot import BaseRobot
from app.modules.robots.common.utils import safe_str
from app.modules.tinvest.facade import TInvestFacade
from app.modules.tinvest.service import TInvestService
from app.modules.tinvest import queries as tinvest_queries


class PortfolioUpdaterRobot(BaseRobot):
    """Робот для обновления портфеля пользователя"""

    def __init__(self, robot_name: str = "tinvest"):
        super().__init__(
            robot_type="portfolio_updater",
            robot_name=robot_name,
            version="2.0.0"
        )

    async def execute(
            self,
            robot_id: int,
            user_id: int,
            token_id: int,
            token: str,
            **kwargs
    ) -> Dict[str, Any]:
        """Основная работа робота"""
        start_time = datetime.now(timezone.utc)

        self.log.info(f"🚀 Начало работы для робота {robot_id}")

        facade = TInvestFacade(token)

        started_at = datetime.now(timezone.utc)
        self.log.info("📋 Запрос списка счетов...")

        try:
            accounts_raw = await facade.get_accounts()

            await self.log_api_call(
                endpoint="tinkoff.public.invest.api.contract.v1.UsersService/GetAccounts",
                request_data={"status": "ACCOUNT_STATUS_UNSPECIFIED"},
                response_data={"accounts_count": len(accounts_raw)},
                response_status=200,
                token_id=token_id,
                user_id=user_id,
                started_at=started_at
            )
        except Exception as e:
            await self.log_api_call(
                endpoint="tinkoff.public.invest.api.contract.v1.UsersService/GetAccounts",
                error_message=str(e),
                token_id=token_id,
                user_id=user_id,
                started_at=started_at
            )
            raise

        if not accounts_raw:
            self.log.info("📭 Счетов не найдено")
            return {"status": "success", "accounts_found": 0, "portfolios_updated": 0, "snapshots_saved": 0}

        self.log.info(f"📊 Найдено счетов: {len(accounts_raw)}")

        accounts = []
        for acc in accounts_raw:
            accounts.append({
                "id": acc.get("id"),
                "type": safe_str(acc.get("type", "")).replace("ACCOUNT_TYPE_", ""),
                "name": safe_str(acc.get("name", "")),
                "status": safe_str(acc.get("status", "")).replace("ACCOUNT_STATUS_", ""),
                "opened_date": acc.get("openedDate"),
                "closed_date": acc.get("closedDate")
            })

        portfolios_updated = 0
        snapshots_saved = 0
        tinvest_svc = TInvestService()

        for account in accounts:
            try:
                self.log.info(f"  → Счет {account['id']} ({account['name']})")

                portfolio_started = datetime.now(timezone.utc)
                portfolio_data = await facade.get_portfolio(account["id"])

                await self.log_api_call(
                    endpoint="tinkoff.public.invest.api.contract.v1.OperationsService/GetPortfolio",
                    request_data={"accountId": account["id"]},
                    response_data={
                        "total_amount": portfolio_data.get("total_amount_portfolio", {}).get("decimal"),
                        "positions_count": len(portfolio_data.get("positions", []))
                    },
                    response_status=200,
                    token_id=token_id,
                    user_id=user_id,
                    started_at=portfolio_started
                )

                # Сохраняем снимок
                snapshot_id = await tinvest_svc.save_portfolio_snapshot(
                    db=self.db,
                    user_id=user_id,
                    account_id=account["id"],
                    account_data=account,
                    portfolio_data={"portfolio": portfolio_data}
                )

                if snapshot_id:
                    self.log.info(f"    ✓ Снимок сохранен (ID: {snapshot_id})")
                    account_in_db = tinvest_svc._execute(
                        tinvest_queries.build_get_account_by_id_query(),
                        {"user_id": user_id, "account_id": account["id"]},
                        fetch_one=True,
                    )
                    if account_in_db:
                        tinvest_svc._execute(
                            tinvest_queries.build_update_account_sync_time_query(),
                            {
                                "account_id": account_in_db[0],
                                "now": datetime.now(timezone.utc),
                                "token_id": token_id,
                            },
                        )
                        self.db.commit()
                    snapshots_saved += 1
                else:
                    self.log.warning(f"    ⚠️ Снимок не сохранен")

            except Exception as e:
                self.log.error(f"    ❌ Ошибка: {e}")

            portfolios_updated += 1

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        self.log.info(f"✅ Работа завершена. Счетов: {portfolios_updated}, снимков: {snapshots_saved}")

        return {
            "status": "success",
            "accounts_found": len(accounts),
            "portfolios_updated": portfolios_updated,
            "snapshots_saved": snapshots_saved,
            "execution_time_ms": int(execution_time)
        }