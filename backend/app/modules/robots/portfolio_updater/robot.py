"""
Робот для обновления портфеля пользователя
"""
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
import json
from sqlalchemy import text

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

        caller = str(kwargs.get("caller") or "scheduler")
        write_daily_universe = caller == "trading_robot"
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
                        # Синхронизация операций: от последней операции в БД до текущего момента.
                        latest_op = tinvest_svc._execute(
                            tinvest_queries.build_get_latest_operation_date_query(),
                            {"account_db_id": account_in_db[0]},
                            fetch_one=True,
                        )
                        from_dt = (
                            latest_op[0]
                            if latest_op and latest_op[0]
                            else (datetime.now(timezone.utc) - timedelta(days=30))
                        )
                        to_dt = datetime.now(timezone.utc)
                        try:
                            sync_result = await tinvest_svc.sync_account_operations(
                                db=self.db,
                                user_id=user_id,
                                external_account_id=account["id"],
                                from_dt=from_dt,
                                to_dt=to_dt,
                                token_id=token_id,
                            )
                            self.log.info(
                                "    ↻ Операции синхронизированы: saved=%s, received=%s, period=%s..%s",
                                sync_result.get("saved_operations"),
                                sync_result.get("total_received"),
                                from_dt.isoformat(),
                                to_dt.isoformat(),
                            )
                        except Exception as e:
                            self.log.warning(f"    ⚠️ Не удалось синхронизировать операции: {e}")
                        self.db.commit()
                    if write_daily_universe:
                        self._sync_daily_universe_from_portfolio(
                            robot_id=robot_id,
                            portfolio_data=portfolio_data,
                            snapshot_id=snapshot_id,
                        )
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

    def _sync_daily_universe_from_portfolio(self, robot_id: int, portfolio_data: Dict[str, Any], snapshot_id: int) -> None:
        positions = list(portfolio_data.get("positions") or [])
        if not positions:
            return
        today = datetime.now(timezone.utc).date()
        insert_sql = text(
            f"""
            INSERT INTO {self.schema}.daily_universe
            (robot_id, trade_date, ticker, source, filter_result, reject_reason, snapshot_id, created_at)
            VALUES
            (:robot_id, :trade_date, :ticker, 'PORTFOLIO', 'ACCEPT', 'В портфеле', :snapshot_id, :created_at)
            ON CONFLICT (robot_id, trade_date, ticker)
            DO UPDATE SET
                source = EXCLUDED.source,
                filter_result = EXCLUDED.filter_result,
                reject_reason = EXCLUDED.reject_reason,
                snapshot_id = EXCLUDED.snapshot_id
            """
        )
        now = datetime.now(timezone.utc)
        for p in positions:
            try:
                qty = float((p.get("quantity") or {}).get("decimal") or 0)
            except Exception:
                qty = 0.0
            if qty <= 0:
                continue
            ticker = (p.get("ticker") or p.get("figi") or "").strip().upper()
            if not ticker:
                continue
            self.db.execute(
                insert_sql,
                {
                    "robot_id": robot_id,
                    "trade_date": today,
                    "ticker": ticker,
                    "snapshot_id": snapshot_id,
                    "created_at": now,
                },
            )
        self.db.commit()