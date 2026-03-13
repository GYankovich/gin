from typing import Optional, List
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

# Импортируем из methods
from app.modules.tinvest.methods import create_tbank_client
from .token_service import token_service

logger = logging.getLogger(__name__)


class TInvestService:
    """Сервис для работы с T-Invest API"""

    @staticmethod
    async def get_user_token(db: Session, user_id: int) -> Optional[str]:
        """
        Получение активного токена пользователя
        """
        return await token_service.get_user_token(db, user_id)

    @staticmethod
    def _parse_money_value(money_value: dict) -> dict:
        """Парсинг MoneyValue в словарь"""
        if not money_value:
            return None

        units = int(money_value.get("units", 0))
        nano = money_value.get("nano", 0)
        decimal_value = units + nano / 1e9

        return {
            "currency": money_value.get("currency", "RUB").upper(),
            "units": units,
            "nano": nano,
            "decimal": round(decimal_value, 2)
        }

    @staticmethod
    def _parse_quotation(quotation: dict) -> dict:
        """Парсинг Quotation в словарь"""
        if not quotation:
            return None

        units = int(quotation.get("units", 0))
        nano = quotation.get("nano", 0)
        decimal_value = units + nano / 1e9

        return {
            "units": units,
            "nano": nano,
            "decimal": round(decimal_value, 4)
        }

    @staticmethod
    def _parse_portfolio_position(position: dict) -> dict:
        """Парсинг позиции портфеля"""
        return {
            "figi": position.get("figi"),
            "instrument_type": position.get("instrumentType", ""),
            "quantity": TInvestService._parse_quotation(position.get("quantity")),
            "average_position_price": TInvestService._parse_money_value(position.get("averagePositionPrice")),
            "current_price": TInvestService._parse_money_value(position.get("currentPrice")),
            "expected_yield": TInvestService._parse_quotation(position.get("expectedYield")),
            "daily_yield": TInvestService._parse_money_value(position.get("dailyYield")),
            "blocked": position.get("blocked", False),
            "ticker": position.get("ticker"),
            "class_code": position.get("classCode"),
            "position_uid": position.get("positionUid"),
            "instrument_uid": position.get("instrumentUid")
        }

    @staticmethod
    async def get_accounts(token: str) -> List[dict]:
        """
        Получение списка счетов пользователя
        """
        client = create_tbank_client(token)
        accounts = await client.get_accounts()

        result = []
        for acc in accounts:
            result.append({
                "id": acc.get("id"),
                "type": acc.get("type", "").replace("ACCOUNT_TYPE_", ""),
                "name": acc.get("name", ""),
                "status": acc.get("status", "").replace("ACCOUNT_STATUS_", ""),
                "opened_date": acc.get("openedDate"),
                "closed_date": acc.get("closedDate"),
                "access_level": acc.get("accessLevel", "").replace("ACCOUNT_ACCESS_LEVEL_", "")
            })

        return result

    @staticmethod
    async def get_portfolio_data(token: str, account_id: Optional[str] = None) -> dict:
        """
        Получение данных портфеля
        """
        try:
            client = create_tbank_client(token)

            # Получаем список счетов
            accounts = await TInvestService.get_accounts(token)

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
                "total_amount_portfolio": TInvestService._parse_money_value(portfolio_result.get("totalAmountPortfolio")),
                "total_amount_shares": TInvestService._parse_money_value(portfolio_result.get("totalAmountShares")),
                "total_amount_bonds": TInvestService._parse_money_value(portfolio_result.get("totalAmountBonds")),
                "total_amount_etf": TInvestService._parse_money_value(portfolio_result.get("totalAmountEtf")),
                "total_amount_currencies": TInvestService._parse_money_value(portfolio_result.get("totalAmountCurrencies")),
                "total_amount_futures": TInvestService._parse_money_value(portfolio_result.get("totalAmountFutures")),
                "total_amount_options": TInvestService._parse_money_value(portfolio_result.get("totalAmountOptions")),
                "expected_yield": TInvestService._parse_quotation(portfolio_result.get("expectedYield")),
                "daily_yield": TInvestService._parse_money_value(portfolio_result.get("dailyYield")),
                "daily_yield_relative": TInvestService._parse_quotation(portfolio_result.get("dailyYieldRelative")),
                "positions": [
                    TInvestService._parse_portfolio_position(pos)
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

    @staticmethod
    async def save_portfolio_snapshot(
            db: Session,
            user_id: int,
            account_id: str,
            account_data: dict,
            portfolio_data: dict
    ) -> Optional[int]:
        """
        Сохраняет снимок портфеля в базу данных
        """
        try:
            # Находим или создаем запись счета
            account_query = text("""
                                 SELECT id FROM ganaly.portfolio_accounts
                                 WHERE user_id = :user_id AND account_id = :account_id
                                 """)

            result = db.execute(
                account_query,
                {"user_id": user_id, "account_id": account_id}
            ).first()

            if not result:
                # Создаем новую запись счета
                insert_account = text("""
                                      INSERT INTO ganaly.portfolio_accounts
                                      (user_id, account_id, account_type, account_name, account_status, opened_date, is_active)
                                      VALUES
                                          (:user_id, :account_id, :account_type, :account_name, :account_status, :opened_date, 1)
                                          RETURNING id
                                      """)

                account = db.execute(
                    insert_account,
                    {
                        "user_id": user_id,
                        "account_id": account_id,
                        "account_type": account_data.get("type", ""),
                        "account_name": account_data.get("name", ""),
                        "account_status": account_data.get("status", ""),
                        "opened_date": account_data.get("opened_date"),
                    }
                ).first()
                db_account_id = account[0]
                logger.info(f"Created new portfolio account {account_id} for user {user_id}")
            else:
                db_account_id = result[0]

            # Сохраняем снимок портфеля
            portfolio = portfolio_data["portfolio"]

            insert_snapshot = text("""
                                   INSERT INTO ganaly.portfolio_snapshots
                                   (account_id, snapshot_date, total_amount_portfolio, total_amount_shares,
                                    total_amount_bonds, total_amount_etf, total_amount_currencies,
                                    total_amount_futures, total_amount_options, expected_yield,
                                    daily_yield, daily_yield_relative, currency)
                                   VALUES
                                       (:account_id, :snapshot_date, :total_amount_portfolio, :total_amount_shares,
                                        :total_amount_bonds, :total_amount_etf, :total_amount_currencies,
                                        :total_amount_futures, :total_amount_options, :expected_yield,
                                        :daily_yield, :daily_yield_relative, :currency)
                                       RETURNING id
                                   """)

            snapshot = db.execute(
                insert_snapshot,
                {
                    "account_id": db_account_id,
                    "snapshot_date": datetime.utcnow(),
                    "total_amount_portfolio": portfolio["total_amount_portfolio"]["decimal"],
                    "total_amount_shares": portfolio.get("total_amount_shares", {}).get("decimal"),
                    "total_amount_bonds": portfolio.get("total_amount_bonds", {}).get("decimal"),
                    "total_amount_etf": portfolio.get("total_amount_etf", {}).get("decimal"),
                    "total_amount_currencies": portfolio.get("total_amount_currencies", {}).get("decimal"),
                    "total_amount_futures": portfolio.get("total_amount_futures", {}).get("decimal"),
                    "total_amount_options": portfolio.get("total_amount_options", {}).get("decimal"),
                    "expected_yield": portfolio.get("expected_yield", {}).get("decimal"),
                    "daily_yield": portfolio.get("daily_yield", {}).get("decimal"),
                    "daily_yield_relative": portfolio.get("daily_yield_relative", {}).get("decimal"),
                    "currency": portfolio["total_amount_portfolio"]["currency"]
                }
            ).first()

            snapshot_id = snapshot[0]

            # Сохраняем позиции
            for pos in portfolio["positions"]:
                insert_position = text("""
                                       INSERT INTO ganaly.portfolio_positions
                                       (snapshot_id, figi, instrument_type, quantity,
                                        average_position_price, current_price, expected_yield,
                                        daily_yield, blocked, ticker, class_code,
                                        position_uid, instrument_uid)
                                       VALUES
                                           (:snapshot_id, :figi, :instrument_type, :quantity,
                                            :average_position_price, :current_price, :expected_yield,
                                            :daily_yield, :blocked, :ticker, :class_code,
                                            :position_uid, :instrument_uid)
                                       """)

                db.execute(
                    insert_position,
                    {
                        "snapshot_id": snapshot_id,
                        "figi": pos.get("figi"),
                        "instrument_type": pos["instrument_type"],
                        "quantity": pos["quantity"]["decimal"],
                        "average_position_price": pos.get("average_position_price", {}).get("decimal"),
                        "current_price": pos.get("current_price", {}).get("decimal"),
                        "expected_yield": pos.get("expected_yield", {}).get("decimal"),
                        "daily_yield": pos.get("daily_yield", {}).get("decimal"),
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

    @staticmethod
    async def refresh_all_portfolios(db: Session, user_id: int) -> dict:
        """
        Получение всех счетов и портфелей пользователя с сохранением в БД
        Использует существующий метод get_portfolio_data для каждого счета
        """
        token = await TInvestService.get_user_token(db, user_id)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Токен T-Invest не найден. Добавьте токен в настройках."
            )

        # Получаем все счета
        accounts = await TInvestService.get_accounts(token)

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
                portfolio_data = await TInvestService.get_portfolio_data(token, account["id"])

                # Сохраняем снимок в БД
                snapshot_id = await TInvestService.save_portfolio_snapshot(
                    db=db,
                    user_id=user_id,
                    account_id=account["id"],
                    account_data=account,
                    portfolio_data=portfolio_data
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

        return {
            "total_accounts": len(accounts),
            "portfolios_loaded": len([p for p in portfolios if p.get("portfolio")]),
            "snapshots_saved": snapshots_saved,
            "accounts": accounts,
            "portfolios": portfolios
        }

    @staticmethod
    async def update_token_last_used(db: Session, token_id: int):
        """
        Обновление времени последнего использования токена
        """
        try:
            query = text("""
                         UPDATE ganaly.api_tokens
                         SET last_used_at = :now
                         WHERE id = :token_id
                         """)

            db.execute(
                query,
                {
                    "token_id": token_id,
                    "now": datetime.now(timezone.utc)
                }
            )
            db.commit()

            logger.info(f"✅ Updated last_used_at for token {token_id}")

        except Exception as e:
            logger.error(f"❌ Error updating token last_used_at: {e}")
            db.rollback()
            raise


# Создаем экземпляр сервиса
tinvest_service = TInvestService()