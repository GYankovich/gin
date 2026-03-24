# app/modules/robots/portfolio_updater/robot.py
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.modules.robots.base.base_robot import BaseRobot
from app.modules.tinvest.methods import create_tbank_client
from app.modules.tinvest import utils as tinvest_utils
from app.modules.tinvest.service import TInvestService


class PortfolioUpdaterRobot(BaseRobot):
    """
    Робот для обновления портфеля пользователя
    """

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
        """
        Основная работа робота
        """
        start_time = datetime.now(timezone.utc)

        self.log.info(f"🚀 Начало работы для робота {robot_id}")

        # Создаем клиент T-Invest
        client = create_tbank_client(token)

        # Получаем счета (с логированием запроса)
        self.log.info("📋 Запрос списка счетов...")
        accounts_raw = await self._get_accounts_with_logging(client, token_id, user_id)

        if not accounts_raw:
            self.log.info("📭 Счетов не найдено")
            return {
                "status": "success",
                "accounts_found": 0,
                "portfolios_updated": 0,
                "snapshots_saved": 0
            }

        self.log.info(f"📊 Найдено счетов: {len(accounts_raw)}")

        # Преобразуем в удобный формат
        accounts = self._parse_accounts(accounts_raw)

        # Обрабатываем каждый счет
        portfolios_updated = 0
        snapshots_saved = 0

        for account in accounts:
            success, snapshot_id = await self._process_account(
                account, token, user_id, token_id
            )
            portfolios_updated += 1
            if snapshot_id:
                snapshots_saved += 1

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        self.log.info(f"✅ Работа завершена. Счетов: {portfolios_updated}, снимков: {snapshots_saved}")

        return {
            "status": "success",
            "accounts_found": len(accounts),
            "portfolios_updated": portfolios_updated,
            "snapshots_saved": snapshots_saved,
            "execution_time_ms": int(execution_time)
        }

    # ============================================================
    # Приватные методы
    # ============================================================


    async def _get_accounts_with_logging(
            self,
            client,
            token_id: int,
            user_id: int
    ) -> List[Dict]:
        """
        Получение счетов с логированием запроса
        """
        started_at = datetime.now(timezone.utc)
        endpoint = "tinkoff.public.invest.api.contract.v1.UsersService/GetAccounts"
        request_data = {"status": "ACCOUNT_STATUS_UNSPECIFIED"}

        try:
            # Выполняем запрос
            accounts = await client.get_accounts()

            # Логируем успешный запрос с полными данными
            await self._log_api_call(
                endpoint=endpoint,
                request_data=request_data,
                response_data={
                    "accounts": [  # передаем полные данные для файлового лога
                        {
                            "id": acc.get("id"),
                            "type": acc.get("type"),
                            "name": acc.get("name")
                        }
                        for acc in accounts
                    ],
                    "count": len(accounts)
                },
                response_status=200,
                token_id=token_id,
                user_id=user_id,
                started_at=started_at
            )

            return accounts

        except Exception as e:
            error_msg = str(e)

            await self._log_api_call(
                endpoint=endpoint,
                request_data=request_data,
                error_message=error_msg,
                token_id=token_id,
                user_id=user_id,
                started_at=started_at
            )

            raise

    async def _process_account(
            self,
            account: dict,
            token: str,
            user_id: int,
            token_id: int
    ) -> tuple[bool, Optional[int]]:
        """
        Обработка одного счета
        """
        try:
            self.log.info(f"  → Счет {account['id']} ({account['name']})")

            portfolio_data = await self._get_portfolio_with_logging(
                token, account["id"], token_id, user_id
            )

            if not portfolio_data:
                self.log.warning(f"    ⚠️ Не удалось получить портфель")
                return False, None

            tinvest_svc = TInvestService()

            # Сохраняем снимок - используем глобальный экземпляр сервиса
            snapshot_id = await tinvest_svc.save_portfolio_snapshot(
                db=self.db,  # передаем текущую сессию
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
            self.log.error(f"    ❌ Ошибка: {e}", exc_info=True)
            return False, None


    async def _get_portfolio_with_logging(
            self,
            token: str,
            account_id: str,
            token_id: int,
            user_id: int
    ) -> Optional[Dict]:
        """
        Получение портфеля с логированием запроса
        """
        client = create_tbank_client(token)
        started_at = datetime.now(timezone.utc)
        endpoint = "tinkoff.public.invest.api.contract.v1.OperationsService/GetPortfolio"
        request_data = {"accountId": account_id, "currency": "RUB"}

        try:
            # Выполняем запрос
            portfolio_result = await client.get_portfolio(account_id)

            # Парсим данные для сохранения в БД
            portfolio_data = {
                "total_amount_portfolio": tinvest_utils.parse_money_value(
                    portfolio_result.get("totalAmountPortfolio")
                ),
                "total_amount_shares": tinvest_utils.parse_money_value(
                    portfolio_result.get("totalAmountShares")
                ),
                "total_amount_bonds": tinvest_utils.parse_money_value(
                    portfolio_result.get("totalAmountBonds")
                ),
                "total_amount_etf": tinvest_utils.parse_money_value(
                    portfolio_result.get("totalAmountEtf")
                ),
                "total_amount_currencies": tinvest_utils.parse_money_value(
                    portfolio_result.get("totalAmountCurrencies")
                ),
                "total_amount_futures": tinvest_utils.parse_money_value(
                    portfolio_result.get("totalAmountFutures")
                ),
                "total_amount_options": tinvest_utils.parse_money_value(
                    portfolio_result.get("totalAmountOptions")
                ),
                "expected_yield": tinvest_utils.parse_quotation(
                    portfolio_result.get("expectedYield")
                ),
                "daily_yield": tinvest_utils.parse_money_value(
                    portfolio_result.get("dailyYield")
                ),
                "daily_yield_relative": tinvest_utils.parse_quotation(
                    portfolio_result.get("dailyYieldRelative")
                ),
                "positions": [
                    tinvest_utils.parse_portfolio_position(pos)
                    for pos in portfolio_result.get("positions", [])
                ]
            }

            # Логируем успешный запрос с полными данными для файлового лога
            await self._log_api_call(
                endpoint=endpoint,
                request_data=request_data,
                response_data={
                    "total_amount": portfolio_data["total_amount_portfolio"],
                    "positions_count": len(portfolio_data["positions"]),
                    "positions": [  # первые 5 позиций для лога
                        {
                            "figi": p.get("figi"),
                            "ticker": p.get("ticker"),
                            "quantity": p.get("quantity"),
                            "current_price": p.get("current_price")
                        }
                        for p in portfolio_data["positions"][:5]
                    ],
                    "positions_total": len(portfolio_data["positions"])
                },
                response_status=200,
                token_id=token_id,
                user_id=user_id,
                started_at=started_at
            )

            return {"portfolio": portfolio_data}

        except Exception as e:
            error_msg = str(e)

            await self._log_api_call(
                endpoint=endpoint,
                request_data=request_data,
                error_message=error_msg,
                token_id=token_id,
                user_id=user_id,
                started_at=started_at
            )

            raise

    def _parse_accounts(self, accounts_raw: List[Dict]) -> List[Dict]:
        """Преобразует сырые данные счетов в удобный формат"""
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
        return accounts