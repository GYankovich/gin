# app/modules/tinvest/service.py
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

# Импортируем из methods
from app.modules.tinvest.methods import create_tbank_client
from .token_service import token_service
from . import queries, utils

logger = logging.getLogger(__name__)


class TInvestService:
    """Сервис для работы с T-Invest API"""

    def __init__(self):
        self.db: Optional[Session] = None

    def _execute(self, query: str, params: dict, fetch_one: bool = False):
        """Утилита для выполнения запросов"""
        result = self.db.execute(text(query), params)
        return result.first() if fetch_one else result

    async def get_user_token(self, db: Session, user_id: int) -> Optional[str]:
        """
        Получение активного токена пользователя
        """
        return await token_service.get_user_token(db, user_id)

    async def get_accounts(self, token: str) -> List[dict]:
        """
        Получение списка счетов пользователя
        """
        client = create_tbank_client(token)
        accounts = await client.get_accounts()

        result = []
        for acc in accounts:
            result.append({
                "id": acc.get("id"),
                "type": utils.safe_str(acc.get("type", "")).replace("ACCOUNT_TYPE_", ""),
                "name": utils.safe_str(acc.get("name", "")),
                "status": utils.safe_str(acc.get("status", "")).replace("ACCOUNT_STATUS_", ""),
                "opened_date": acc.get("openedDate"),
                "closed_date": acc.get("closedDate"),
                "access_level": utils.safe_str(acc.get("accessLevel", "")).replace("ACCOUNT_ACCESS_LEVEL_", "")
            })

        return result

    async def get_portfolio_data(
            self,
            token: str,
            account_id: Optional[str] = None
    ) -> dict:
        """
        Получение данных портфеля
        """
        try:
            client = create_tbank_client(token)

            # Получаем список счетов
            accounts = await self.get_accounts(token)

            if not accounts:
                logger.warning("No accounts found for user")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="У пользователя нет счетов в Т-Банке. Откройте счет в приложении Т-Инвестиции."
                )

            if not account_id:
                account_id = accounts[0].get("id")
                logger.info(f"Using first account: {account_id}")

            # Находим информацию о счете
            account_info = None
            for acc in accounts:
                if acc.get("id") == account_id:
                    account_info = acc
                    break

            if not account_info:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Счет {account_id} не найден"
                )

            # Запрашиваем портфель
            portfolio_result = await client.get_portfolio(account_id)

            # Формируем данные портфеля
            portfolio_data = {
                "total_amount_portfolio": utils.parse_money_value(portfolio_result.get("totalAmountPortfolio")),
                "total_amount_shares": utils.parse_money_value(portfolio_result.get("totalAmountShares")),
                "total_amount_bonds": utils.parse_money_value(portfolio_result.get("totalAmountBonds")),
                "total_amount_etf": utils.parse_money_value(portfolio_result.get("totalAmountEtf")),
                "total_amount_currencies": utils.parse_money_value(portfolio_result.get("totalAmountCurrencies")),
                "total_amount_futures": utils.parse_money_value(portfolio_result.get("totalAmountFutures")),
                "total_amount_options": utils.parse_money_value(portfolio_result.get("totalAmountOptions")),
                "expected_yield": utils.parse_quotation(portfolio_result.get("expectedYield")),
                "daily_yield": utils.parse_money_value(portfolio_result.get("dailyYield")),
                "daily_yield_relative": utils.parse_quotation(portfolio_result.get("dailyYieldRelative")),
                "positions": [
                    utils.parse_portfolio_position(pos)
                    for pos in portfolio_result.get("positions", [])
                ]
            }

            logger.info(f"Successfully parsed portfolio data for account {account_id}")

            return {
                "account": account_info,
                "portfolio": portfolio_data,
                "last_updated": datetime.utcnow().isoformat() + "Z"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in get_portfolio_data: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Ошибка при получении портфеля: {str(e)}"
            )

    async def save_portfolio_snapshot(
            self,
            db: Session,
            user_id: int,
            account_id: str,
            account_data: dict,
            portfolio_data: dict
    ) -> Optional[int]:
        """
        Сохраняет снимок портфеля в базу данных
        """
        self.db = db

        try:
            # Находим или создаем запись счета
            account_query = queries.build_get_account_by_id_query()
            result = self._execute(
                account_query,
                {"user_id": user_id, "account_id": account_id},
                fetch_one=True
            )

            if not result:
                # Создаем новую запись счета
                insert_account = queries.build_create_account_query()
                account = self._execute(
                    insert_account,
                    {
                        "user_id": user_id,
                        "account_id": account_id,
                        "account_type": account_data.get("type", ""),
                        "account_name": account_data.get("name", ""),
                        "account_status": account_data.get("status", ""),
                        "opened_date": account_data.get("opened_date"),
                    },
                    fetch_one=True
                )
                db_account_id = account[0]
                logger.info(f"Created new portfolio account {account_id} for user {user_id}")
            else:
                db_account_id = result[0]
                # Обновляем информацию о счете
                update_account = queries.build_update_account_query()
                self._execute(
                    update_account,
                    {
                        "db_account_id": db_account_id,
                        "account_name": account_data.get("name", ""),
                        "account_status": account_data.get("status", ""),
                        "now": datetime.now(timezone.utc)
                    }
                )

            # Сохраняем снимок портфеля
            portfolio = portfolio_data["portfolio"]

            insert_snapshot = queries.build_create_snapshot_query()
            snapshot = self._execute(
                insert_snapshot,
                {
                    "account_id": db_account_id,
                    "snapshot_date": datetime.utcnow(),
                    "total_amount_portfolio": utils.safe_float(portfolio["total_amount_portfolio"].get("decimal") if portfolio["total_amount_portfolio"] else None),
                    "total_amount_shares": utils.safe_float(portfolio.get("total_amount_shares", {}).get("decimal")),
                    "total_amount_bonds": utils.safe_float(portfolio.get("total_amount_bonds", {}).get("decimal")),
                    "total_amount_etf": utils.safe_float(portfolio.get("total_amount_etf", {}).get("decimal")),
                    "total_amount_currencies": utils.safe_float(portfolio.get("total_amount_currencies", {}).get("decimal")),
                    "total_amount_futures": utils.safe_float(portfolio.get("total_amount_futures", {}).get("decimal")),
                    "total_amount_options": utils.safe_float(portfolio.get("total_amount_options", {}).get("decimal")),
                    "expected_yield": utils.safe_float(portfolio.get("expected_yield", {}).get("decimal")),
                    "daily_yield": utils.safe_float(portfolio.get("daily_yield", {}).get("decimal")),
                    "daily_yield_relative": utils.safe_float(portfolio.get("daily_yield_relative", {}).get("decimal")),
                    "currency": portfolio["total_amount_portfolio"]["currency"] if portfolio["total_amount_portfolio"] else "RUB"
                },
                fetch_one=True
            )

            snapshot_id = snapshot[0]

            # Сохраняем позиции
            insert_position = queries.build_create_position_query()
            for pos in portfolio["positions"]:
                self._execute(
                    insert_position,
                    {
                        "snapshot_id": snapshot_id,
                        "figi": pos.get("figi"),
                        "instrument_type": pos["instrument_type"],
                        "quantity": utils.safe_float(pos["quantity"].get("decimal") if pos.get("quantity") else None),
                        "average_position_price": utils.safe_float(pos.get("average_position_price", {}).get("decimal")),
                        "current_price": utils.safe_float(pos.get("current_price", {}).get("decimal")),
                        "expected_yield": utils.safe_float(pos.get("expected_yield", {}).get("decimal")),
                        "daily_yield": utils.safe_float(pos.get("daily_yield", {}).get("decimal")),
                        "blocked": 1 if pos.get("blocked") else 0,
                        "ticker": pos.get("ticker"),
                        "class_code": pos.get("class_code"),
                        "position_uid": pos.get("position_uid"),
                        "instrument_uid": pos.get("instrument_uid")
                    }
                )

            db.commit()
            logger.info(f"Saved portfolio snapshot {snapshot_id} for account {account_id}")
            return snapshot_id

        except Exception as e:
            db.rollback()
            logger.error(f"Error saving portfolio snapshot: {e}")
            return None

    async def refresh_all_portfolios(self, db: Session, user_id: int) -> dict:
        """
        Получение всех счетов и портфелей пользователя с сохранением в БД
        """
        self.db = db

        token = await self.get_user_token(db, user_id)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Токен T-Invest не найден. Добавьте токен в настройках."
            )

        # Получаем все счета
        accounts = await self.get_accounts(token)

        if not accounts:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У пользователя нет счетов"
            )

        # Для каждого счета получаем портфель через существующий метод
        portfolios = []
        snapshots_saved = 0

        for account in accounts:
            try:
                # Используем существующий get_portfolio_data
                portfolio_data = await self.get_portfolio_data(token, account["id"])

                # Сохраняем снимок в БД
                snapshot_id = await self.save_portfolio_snapshot(
                    db=db,
                    user_id=user_id,
                    account_id=account["id"],
                    account_data=account,
                    portfolio_data=portfolio_data
                )

                # Обновляем время синхронизации счета
                if snapshot_id:
                    account_in_db = self._execute(
                        queries.build_get_account_by_id_query(),
                        {"user_id": user_id, "account_id": account["id"]},
                        fetch_one=True
                    )
                    if account_in_db:
                        self._execute(
                            queries.build_update_account_sync_time_query(),
                            {"account_id": account_in_db[0], "now": datetime.now(timezone.utc)}
                        )

                portfolios.append({
                    "account": account,
                    "portfolio": portfolio_data["portfolio"],
                    "snapshot_id": snapshot_id
                })

                if snapshot_id:
                    snapshots_saved += 1

            except Exception as e:
                logger.error(f"Error getting portfolio for account {account['id']}: {e}")
                portfolios.append({
                    "account": account,
                    "error": str(e),
                    "portfolio": None
                })

        db.commit()

        return {
            "total_accounts": len(accounts),
            "portfolios_loaded": len([p for p in portfolios if p.get("portfolio")]),
            "snapshots_saved": snapshots_saved,
            "accounts": accounts,
            "portfolios": portfolios
        }

    async def get_accounts_from_db(self, db: Session, user_id: int) -> List[dict]:
        """
        Получение списка счетов пользователя из БД
        """
        self.db = db
        query = queries.build_get_accounts_list_query()
        results = self._execute(query, {"user_id": user_id}).fetchall()

        accounts = []
        for row in results:
            accounts.append({
                "id": utils.safe_int(row[0]),
                "account_id": utils.safe_str(row[1]),
                "type": utils.safe_str(row[2]),
                "name": utils.safe_str(row[3]),
                "status": utils.safe_str(row[4]),
                "opened_date": row[5],
                "last_sync_at": row[6],
                "created_at": row[7]
            })

        return accounts

    async def get_last_snapshots(
            self,
            db: Session,
            account_id: int,
            limit: int = 10
    ) -> List[dict]:
        """
        Получение последних снимков портфеля из БД
        """
        self.db = db
        query, params = queries.build_get_last_snapshots_query(account_id, limit)
        results = self._execute(query, params).fetchall()

        snapshots = []
        for row in results:
            snapshots.append({
                "id": utils.safe_int(row[0]),
                "snapshot_date": row[1],
                "total_value": utils.safe_float(row[2]),
                "daily_yield": utils.safe_float(row[3], None),
                "expected_yield": utils.safe_float(row[4], None)
            })

        return snapshots


# Создаем экземпляр сервиса
tinvest_service = TInvestService()