# app/modules/tinvest/service.py
from typing import Optional, List, Dict, Any
import json
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

# Импортируем из methods
from app.modules.tinvest.methods import (
    create_tbank_client,
    TBANK_GET_OPERATIONS_BY_CURSOR_ENDPOINT,
)
from .token_service import token_service
from . import queries, utils

logger = logging.getLogger(__name__)


def _json_for_pg(value: Any) -> str:
    """Сериализация для JSON/JSONB в raw SQL (psycopg2 не адаптирует dict)."""
    return json.dumps(value, ensure_ascii=False, default=str)


class TInvestService:
    """Сервис для работы с T-Invest API"""

    def __init__(self):
        self.db: Optional[Session] = None

    def _write_external_api_log(
            self,
            *,
            user_id: int,
            token_id: Optional[int],
            broker: str,
            context_type: Optional[str],
            context_ref: Optional[str],
            endpoint: str,
            request_data: Dict[str, Any],
            response_status: Optional[int],
            response_data: Optional[Dict[str, Any]],
            started_at: datetime,
            finished_at: datetime,
            success: bool,
            error_message: Optional[str],
    ) -> None:
        duration_ms = int(max(0, (finished_at - started_at).total_seconds() * 1000))
        rd = _json_for_pg(response_data if response_data is not None else {})
        self._execute(
            queries.build_insert_external_api_log_query(),
            {
                "user_id": user_id,
                "token_id": token_id,
                "broker": broker,
                "context_type": context_type,
                "context_ref": context_ref,
                "endpoint": endpoint,
                "request_data": _json_for_pg(request_data),
                "response_status": response_status,
                "response_data": rd,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "success": 1 if success else 0,
                "error_message": (error_message[:8000] if error_message else None),
            },
        )

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

        active_token = await token_service.get_active_token(db, user_id)
        if not active_token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Токен T-Invest не найден. Добавьте токен в настройках."
            )
        token = active_token.get("token")
        active_token_id = active_token.get("id")

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
                            {
                                "account_id": account_in_db[0],
                                "now": datetime.now(timezone.utc),
                                "token_id": active_token_id,
                            }
                        )
                        # Автосинхронизация истории операций для консистентности.
                        latest_op = self._execute(
                            queries.build_get_latest_operation_date_query(),
                            {"account_db_id": account_in_db[0]},
                            fetch_one=True,
                        )
                        from_dt = (latest_op[0] - timedelta(days=2)) if latest_op and latest_op[0] else (datetime.now(timezone.utc) - timedelta(days=30))
                        to_dt = datetime.now(timezone.utc)
                        try:
                            await self.sync_account_operations(
                                db=db,
                                user_id=user_id,
                                external_account_id=account["id"],
                                from_dt=from_dt,
                                to_dt=to_dt,
                            )
                        except Exception as e:
                            logger.warning(f"Operations auto-sync failed for account {account['id']}: {e}")

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
                "last_token_id": utils.safe_int(row[7]) if row[7] is not None else None,
                "created_at": row[8]
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

    @staticmethod
    def _parse_money_decimal(value: Optional[Dict[str, Any]]) -> float:
        if not value:
            return 0.0
        units = float(value.get("units", 0) or 0)
        nano = float(value.get("nano", 0) or 0) / 1e9
        return round(units + nano, 6)

    async def sync_account_operations(
            self,
            db: Session,
            user_id: int,
            external_account_id: str,
            from_dt: datetime,
            to_dt: datetime,
            state: str = "OPERATION_STATE_UNSPECIFIED",
            token_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        self.db = db
        token = None
        effective_token_id = token_id
        if token_id is not None:
            token_row = await token_service.get_token_by_id(db, token_id, user_id)
            if not token_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Токен не найден")
            token = token_row.get("token")
        else:
            active_token = await token_service.get_active_token(db, user_id)
            if active_token:
                token = active_token.get("token")
                effective_token_id = active_token.get("id")
        if not token:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Токен T-Invest не найден")

        account_row = self._execute(
            queries.build_get_account_row_by_external_id_query(),
            {"external_account_id": external_account_id, "user_id": user_id},
            fetch_one=True,
        )
        if not account_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден")
        account_db_id = account_row[0]
        external_account_id = account_row[1]

        client = create_tbank_client(token)
        api_started = datetime.now(timezone.utc)
        request_for_log = {
            "accountId": external_account_id,
            "from": from_dt.isoformat().replace("+00:00", "Z"),
            "to": to_dt.isoformat().replace("+00:00", "Z"),
            "state": state,
            "api": "GetOperationsByCursor",
            "pageLimit": 1000,
        }
        payload: Dict[str, Any] = {}
        try:
            payload = await client.get_operations_all_pages(
                external_account_id, from_dt, to_dt, state=state
            )
            api_finished = datetime.now(timezone.utc)
            page_bodies = payload.pop("pages", [])
            response_for_log: Dict[str, Any] = {
                "pageCount": payload.get("pageCount"),
                "rawItemCount": payload.get("rawItemCount"),
                "pages": page_bodies,
            }
            self._write_external_api_log(
                user_id=user_id,
                token_id=effective_token_id,
                broker="tinvest",
                context_type="operations_sync",
                context_ref=external_account_id,
                endpoint=TBANK_GET_OPERATIONS_BY_CURSOR_ENDPOINT,
                request_data=request_for_log,
                response_status=200,
                response_data=response_for_log,
                started_at=api_started,
                finished_at=api_finished,
                success=True,
                error_message=None,
            )
            self.db.commit()
        except Exception as e:
            api_finished = datetime.now(timezone.utc)
            self._write_external_api_log(
                user_id=user_id,
                token_id=effective_token_id,
                broker="tinvest",
                context_type="operations_sync",
                context_ref=external_account_id,
                endpoint=TBANK_GET_OPERATIONS_BY_CURSOR_ENDPOINT,
                request_data=request_for_log,
                response_status=None,
                response_data={},
                started_at=api_started,
                finished_at=api_finished,
                success=False,
                error_message=str(e),
            )
            self.db.commit()
            raise

        operations = payload.get("operations", []) or []

        upsert_query = queries.build_upsert_operation_query()
        saved = 0
        seen_operation_ids: set[str] = set()
        duplicate_operation_ids_skipped = 0
        for op in operations:
            op_id = str(op.get("id") or "").strip()
            if not op_id:
                continue
            if op_id in seen_operation_ids:
                duplicate_operation_ids_skipped += 1
                continue
            seen_operation_ids.add(op_id)

            payment = op.get("payment") or {}
            price = op.get("price") or {}
            extra_data = {
                "type_text": op.get("type"),
                "currency": op.get("currency"),
                "asset_uid": op.get("assetUid"),
                "child_operations": op.get("childOperations") or [],
            }
            self._execute(
                upsert_query,
                {
                    "account_id": account_db_id,
                    "operation_id": op_id,
                    "parent_operation_id": op.get("parentOperationId") or None,
                    "figi": op.get("figi") or None,
                    "instrument_type": op.get("instrumentType") or None,
                    "instrument_uid": op.get("instrumentUid") or None,
                    "position_uid": op.get("positionUid") or None,
                    "operation_type": op.get("operationType") or "OPERATION_TYPE_UNSPECIFIED",
                    "operation_date": datetime.fromisoformat(str(op.get("date")).replace("Z", "+00:00")) if op.get("date") else from_dt,
                    "quantity": float(op.get("quantity") or 0),
                    "quantity_rest": float(op.get("quantityRest") or 0),
                    "price": self._parse_money_decimal(price),
                    "price_currency": (price.get("currency") or op.get("currency") or "RUB").upper(),
                    "payment": self._parse_money_decimal(payment),
                    "payment_currency": (payment.get("currency") or op.get("currency") or "RUB").upper(),
                    "commission": None,
                    "commission_currency": None,
                    "status": op.get("state") or "OPERATION_STATE_UNSPECIFIED",
                    "trades": _json_for_pg(op.get("trades") or []),
                    "extra_data": _json_for_pg(extra_data),
                },
            )
            saved += 1

        self._execute(
            queries.build_update_account_sync_time_query(),
            {
                "account_id": account_db_id,
                "now": datetime.now(timezone.utc),
                "token_id": effective_token_id,
            },
        )
        db.commit()
        return {
            "account_id": account_db_id,
            "external_account_id": external_account_id,
            "token_id": effective_token_id,
            "from": from_dt.isoformat(),
            "to": to_dt.isoformat(),
            "saved_operations": saved,
            "total_received": len(operations),
            "pages_fetched": payload.get("pageCount", 0),
            "raw_items_from_api": payload.get("rawItemCount", len(operations)),
            "duplicate_operation_ids_skipped": duplicate_operation_ids_skipped,
        }

    async def list_account_operations(
            self,
            db: Session,
            user_id: int,
            account_db_id: int,
            from_dt: datetime,
            to_dt: datetime,
            limit: int = 500,
    ) -> List[Dict[str, Any]]:
        self.db = db
        account_row = self._execute(
            queries.build_get_account_row_query(),
            {"account_db_id": account_db_id, "user_id": user_id},
            fetch_one=True,
        )
        if not account_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Счет не найден")
        rows = self._execute(
            queries.build_get_operations_for_account_query(),
            {
                "account_db_id": account_db_id,
                "from_dt": from_dt,
                "to_dt": to_dt,
                "limit": limit,
            },
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            extra = row[10] or {}
            out.append(
                {
                    "operation_id": row[0],
                    "operation_date": row[1],
                    "operation_type": row[2],
                    "figi": row[3],
                    "instrument_type": row[4],
                    "quantity": float(row[5] or 0),
                    "price": float(row[6] or 0),
                    "payment": float(row[7] or 0),
                    "currency": row[8],
                    "status": row[9],
                    "type_text": extra.get("type_text"),
                }
            )
        return out


# Создаем экземпляр сервиса
tinvest_service = TInvestService()