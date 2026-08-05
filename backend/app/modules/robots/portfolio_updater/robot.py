"""
Робот для обновления портфеля пользователя (T-Invest / ByBit — один цикл, разные фасады).
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsPortfolioUpdaterRobot [1]
#/// Исходный модуль `backend/app/modules/robots/portfolio_updater/robot.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
from sqlalchemy import text

from app.modules.robots.base.base_robot import BaseRobot
from app.modules.robots.common.utils import safe_str
from app.modules.robots.trading.brokers.factory import create_broker_facade
from app.modules.robots.trading.brokers.routing import normalize_broker_type
from app.modules.bybit.http_client import BybitApiError
from app.modules.tinvest.utils import parse_api_timestamp
from app.modules.tinvest.service import TInvestService
from app.modules.tinvest import queries as tinvest_queries
from app.core.config import settings


class PortfolioUpdaterRobot(BaseRobot):
    """Робот для обновления портфеля пользователя"""

    def __init__(self, robot_name: str = "tinvest"):
        super().__init__(
            robot_type="portfolio_updater",
            robot_name=robot_name,
            version="2.1.0"
        )

    async def execute(
            self,
            robot_id: int,
            user_id: int,
            token_id: int,
            token: str,
            **kwargs
    ) -> Dict[str, Any]:
        """Основная работа робота: accounts → portfolio → snapshot → operations."""
        start_time = datetime.now(timezone.utc)
        broker_type = normalize_broker_type(str(kwargs.get("broker_type") or "tinvest"))
        self.log.info("🚀 Начало работы для робота %s (broker=%s)", robot_id, broker_type)

        facade = create_broker_facade(
            broker_type,
            token,
            token_extra_data=kwargs.get("token_extra_data") if isinstance(kwargs.get("token_extra_data"), dict) else None,
            robot_config=kwargs.get("robot_config") if isinstance(kwargs.get("robot_config"), dict) else None,
            user_id=user_id,
            token_id=token_id,
            context_type="portfolio_updater",
            context_ref=str(robot_id)
        )

        caller = str(kwargs.get("caller") or "scheduler")
        write_daily_universe = caller == "trading_robot"
        sync_operations = bool(kwargs.get("sync_operations", caller == "scheduler"))
        max_operation_pages = int(kwargs.get("max_operation_pages") or 10)
        portfolios_updated = 0
        snapshots_saved = 0
        portfolio_svc = TInvestService()

        try:
            started_at = datetime.now(timezone.utc)
            self.log.info("📋 Запрос списка счетов...")
            try:
                accounts_raw = await facade.get_accounts()
                await self.log_api_call(
                    endpoint=f"{broker_type}.get_accounts",
                    request_data={},
                    response_data={"accounts_count": len(accounts_raw)},
                    response_status=200,
                    token_id=token_id,
                    user_id=user_id,
                    started_at=started_at
                )
            except Exception as e:
                await self.log_api_call(
                    endpoint=f"{broker_type}.get_accounts",
                    error_message=str(e),
                    token_id=token_id,
                    user_id=user_id,
                    started_at=started_at
                )
                if broker_type == "bybit" and self._is_bybit_auth_error(e):
                    self._handle_bybit_auth_failure(token_id=token_id, user_id=user_id, error=e)
                raise

            if not accounts_raw:
                self.log.info("📭 Счетов не найдено")
                return {"status": "success", "accounts_found": 0, "portfolios_updated": 0, "snapshots_saved": 0}

            self.log.info("📊 Найдено счетов: %s", len(accounts_raw))
            accounts = [self._normalize_account(acc) for acc in accounts_raw]

            for account in accounts:
                try:
                    self.log.info("  → Счет %s (%s)", account["id"], account["name"])
                    portfolio_started = datetime.now(timezone.utc)
                    try:
                        portfolio_data = await facade.get_portfolio(account["id"])
                        await self.log_api_call(
                            endpoint=f"{broker_type}.get_portfolio",
                            request_data={"accountId": account["id"]},
                            response_data={
                                "total_amount": (portfolio_data.get("total_amount_portfolio") or {}).get("decimal"),
                                "positions_count": len(portfolio_data.get("positions") or []),
                            },
                            response_status=200,
                            token_id=token_id,
                            user_id=user_id,
                            started_at=portfolio_started
                        )
                    except Exception as e:
                        await self.log_api_call(
                            endpoint=f"{broker_type}.get_portfolio",
                            request_data={"accountId": account["id"]},
                            error_message=str(e),
                            token_id=token_id,
                            user_id=user_id,
                            started_at=portfolio_started
                        )
                        raise

                    self.log.info("    💾 Сохранение снимка портфеля в БД...")
                    snapshot_id = await portfolio_svc.save_portfolio_snapshot(
                        db=self.db,
                        user_id=user_id,
                        account_id=account["id"],
                        account_data=account,
                        portfolio_data={"portfolio": portfolio_data}
                    )

                    if snapshot_id:
                        self.log.info("    ✓ Снимок сохранен (ID: %s)", snapshot_id)
                        account_in_db = portfolio_svc._execute(
                            tinvest_queries.build_get_account_by_id_query(),
                            {"user_id": user_id, "account_id": account["id"]},
                            fetch_one=True
                        )
                        if account_in_db:
                            portfolio_svc._execute(
                                tinvest_queries.build_update_account_sync_time_query(),
                                {
                                    "account_id": account_in_db[0],
                                    "now": datetime.now(timezone.utc),
                                    "token_id": token_id,
                                }
                            )
                            if sync_operations:
                                await self._sync_operations_for_account(
                                    facade=facade,
                                    portfolio_svc=portfolio_svc,
                                    broker_type=broker_type,
                                    user_id=user_id,
                                    token_id=token_id,
                                    account=account,
                                    max_operation_pages=max_operation_pages
                                )
                                await self._sync_orders_for_account(
                                    facade=facade,
                                    portfolio_svc=portfolio_svc,
                                    broker_type=broker_type,
                                    user_id=user_id,
                                    robot_id=robot_id,
                                    account=account
                                )
                            else:
                                self.log.info("    ↻ Синхронизация операций пропущена (быстрый режим)")
                        if write_daily_universe:
                            self._sync_daily_universe_from_portfolio(
                                robot_id=robot_id,
                                portfolio_data=portfolio_data,
                                snapshot_id=snapshot_id
                            )
                        snapshots_saved += 1
                    else:
                        self.log.warning("    ⚠️ Снимок не сохранен")

                except Exception as e:
                    self.log.error("    ❌ Ошибка: %s", e)
                    if broker_type == "bybit" and self._is_bybit_auth_error(e):
                        # Only kill the token when the key itself is dead (not FUND/COPY ACL).
                        self._handle_bybit_auth_failure(token_id=token_id, user_id=user_id, error=e)
                    elif broker_type == "bybit" and self._is_bybit_permission_error(e):
                        self.log.warning(
                            "    ↷ ByBit permission gap on account %s — skip account, keep token active",
                            account.get("id")
                        )

                portfolios_updated += 1

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            self.log.info("✅ Работа завершена. Счетов: %s, снимков: %s", portfolios_updated, snapshots_saved)
            return {
                "status": "success",
                "accounts_found": len(accounts),
                "portfolios_updated": portfolios_updated,
                "snapshots_saved": snapshots_saved,
                "execution_time_ms": int(execution_time),
            }
        finally:
            try:
                await facade.close()
            except Exception:
                pass

    @staticmethod
    def _normalize_account(acc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": acc.get("id"),
            "type": safe_str(acc.get("type", "")).replace("ACCOUNT_TYPE_", ""),
            "name": safe_str(acc.get("name", "")),
            "status": safe_str(acc.get("status", "")).replace("ACCOUNT_STATUS_", "") or "OPEN",
            "opened_date": parse_api_timestamp(acc.get("opened_date") or acc.get("openedDate")),
            "closed_date": parse_api_timestamp(acc.get("closed_date") or acc.get("closedDate")),
        }

    async def _sync_operations_for_account(
            self,
            *,
            facade,
            portfolio_svc: TInvestService,
            broker_type: str,
            user_id: int,
            token_id: int,
            account: Dict[str, Any],
            max_operation_pages: int
    ) -> None:
        account_in_db = portfolio_svc._execute(
            tinvest_queries.build_get_account_by_id_query(),
            {"user_id": user_id, "account_id": account["id"]},
            fetch_one=True
        )
        if not account_in_db:
            return
        latest_op = portfolio_svc._execute(
            tinvest_queries.build_get_latest_operation_date_query(),
            {"account_db_id": account_in_db[0]},
            fetch_one=True
        )
        from_dt = (
            latest_op[0]
            if latest_op and latest_op[0]
            else (datetime.now(timezone.utc) - timedelta(days=7))
        )
        to_dt = datetime.now(timezone.utc)
        self.log.info(
            "    ↻ Синхронизация операций %s..%s (макс. %s стр.)...",
            from_dt.isoformat(),
            to_dt.isoformat(),
            max_operation_pages
        )
        ops_started = datetime.now(timezone.utc)
        try:
            operations = await facade.get_operations(
                account["id"],
                from_dt,
                to_dt,
                max_pages=max_operation_pages
            )
            await self.log_api_call(
                endpoint=f"{broker_type}.get_operations",
                request_data={
                    "accountId": account["id"],
                    "from": from_dt.isoformat(),
                    "to": to_dt.isoformat(),
                    "max_pages": max_operation_pages,
                },
                response_data={"operations_count": len(operations or [])},
                response_status=200,
                token_id=token_id,
                user_id=user_id,
                started_at=ops_started
            )
            sync_result = portfolio_svc.sync_account_operations_from_items(
                db=self.db,
                user_id=user_id,
                external_account_id=account["id"],
                from_dt=from_dt,
                to_dt=to_dt,
                operations=list(operations or []),
                token_id=token_id
            )
            self.log.info(
                "    ↻ Операции синхронизированы: saved=%s, received=%s",
                sync_result.get("saved_operations"),
                sync_result.get("total_received")
            )
        except Exception as e:
            await self.log_api_call(
                endpoint=f"{broker_type}.get_operations",
                request_data={"accountId": account["id"]},
                error_message=str(e),
                token_id=token_id,
                user_id=user_id,
                started_at=ops_started
            )
            self.log.warning("    ⚠️ Не удалось синхронизировать операции: %s", e)
            self.db.commit()

    async def _sync_orders_for_account(
            self,
            *,
            facade,
            portfolio_svc: TInvestService,
            broker_type: str,
            user_id: int,
            robot_id: int,
            account: Dict[str, Any]
    ) -> None:
        """Upsert open + history orders into portfolio_orders; Filled → portfolio_operations."""
        from app.modules.portfolio.order_registry import (
            SOURCE_EXTERNAL,
            parse_broker_order_date,
            resolve_portfolio_account_pk,
            upsert_broker_order
        )

        # ByBit: trading orders belong to UNIFIED. FUND/COPY must not import the same
        # linear open/history list (facade ignores account_id → duplicate rows).
        if str(broker_type).lower() == "bybit":
            parse_kind = getattr(facade, "parse_account_kind", None)
            kind = ""
            if callable(parse_kind):
                try:
                    kind = str(parse_kind(str(account.get("id") or "")) or "").strip().upper()
                except Exception:
                    kind = ""
            if not kind:
                aid = str(account.get("id") or "").strip().upper()
                if aid.endswith(":FUND") or aid in {"BYBIT_FUND", "BYBIT:FUND"}:
                    kind = "FUND"
                elif aid.endswith(":COPY") or aid in {"BYBIT_COPY", "BYBIT:COPY"}:
                    kind = "COPY"
                else:
                    kind = "UNIFIED"
            if kind in {"FUND", "COPY"}:
                self.log.info(
                    "    ↻ Заявки: skip %s (ByBit linear orders only on UNIFIED)",
                    account.get("id")
                )
                return

        def _side(row: Dict[str, Any]) -> str:
            s = str(row.get("side") or "").strip().lower()
            if s in {"sell", "order_direction_sell"}:
                return "sell"
            return "buy"

        def _floats(row: Dict[str, Any]):
            try:
                qty = float(row.get("quantity") if row.get("quantity") is not None else row.get("qty") or 0)
            except Exception:
                qty = 0.0
            try:
                price = float(row.get("price") or 0)
            except Exception:
                price = 0.0
            filled = row.get("filled_qty")
            if filled is None:
                filled = row.get("cumExecQty")
            try:
                filled_f = float(filled) if filled is not None else None
            except Exception:
                filled_f = None
            avg = row.get("avg_price")
            if avg is None:
                avg = row.get("avgPrice")
            try:
                avg_f = float(avg) if avg is not None else None
            except Exception:
                avg_f = None
            return qty, price, filled_f, avg_f

        account_in_db = portfolio_svc._execute(
            tinvest_queries.build_get_account_by_id_query(),
            {"user_id": user_id, "account_id": account["id"]},
            fetch_one=True
        )
        if not account_in_db:
            pa_id = resolve_portfolio_account_pk(
                self.db, user_id=int(user_id), broker_account_id=str(account["id"])
            )
        else:
            pa_id = int(account_in_db[0])
        if not pa_id:
            return

        broker_prefix = "tinvest" if str(broker_type).lower() == "tinvest" else "bybit"
        imported = 0
        upserted = 0

        get_orders = getattr(facade, "get_orders", None)
        if callable(get_orders):
            try:
                raw_open = await get_orders(str(account["id"]))
            except Exception as exc:
                self.log.warning("    ⚠️ get_orders failed: %s", exc)
                raw_open = []
            for row in raw_open or []:
                if not isinstance(row, dict):
                    continue
                oid = str(row.get("order_id") or row.get("orderId") or "").strip()
                figi = str(row.get("figi") or row.get("symbol") or "").strip().upper()
                if not oid or not figi:
                    continue
                qty, price, filled_f, avg_f = _floats(row)
                result = upsert_broker_order(
                    self.db,
                    portfolio_account_id=pa_id,
                    order_id=oid,
                    figi=figi,
                    side=_side(row),
                    quantity=qty,
                    status=str(row.get("executionReportStatus") or row.get("status") or "New"),
                    price=price if price > 0 else None,
                    filled_qty=filled_f,
                    avg_price=avg_f,
                    source=SOURCE_EXTERNAL,
                    robot_id=int(robot_id),
                    order_date=parse_broker_order_date(
                        row.get("created_at") or row.get("createdTime") or row.get("updatedTime")
                    ),
                    commit=False,
                    promote_filled=True,
                    broker_prefix=broker_prefix
                )
                if result == "inserted":
                    imported += 1
                elif result == "updated":
                    upserted += 1

        get_hist = getattr(facade, "get_order_history", None)
        if callable(get_hist):
            try:
                raw_hist = await get_hist(str(account["id"]), limit=50)
            except TypeError:
                try:
                    raw_hist = await get_hist(str(account["id"]))
                except Exception as exc:
                    self.log.warning("    ⚠️ get_order_history failed: %s", exc)
                    raw_hist = []
            except Exception as exc:
                self.log.warning("    ⚠️ get_order_history failed: %s", exc)
                raw_hist = []
            for row in raw_hist or []:
                if not isinstance(row, dict):
                    continue
                oid = str(row.get("order_id") or row.get("orderId") or "").strip()
                figi = str(row.get("figi") or row.get("symbol") or "").strip().upper()
                if not oid or not figi:
                    continue
                qty, price, filled_f, avg_f = _floats(row)
                result = upsert_broker_order(
                    self.db,
                    portfolio_account_id=pa_id,
                    order_id=oid,
                    figi=figi,
                    side=_side(row),
                    quantity=qty,
                    status=str(row.get("executionReportStatus") or row.get("status") or ""),
                    price=price if price > 0 else None,
                    filled_qty=filled_f,
                    avg_price=avg_f,
                    source=SOURCE_EXTERNAL,
                    robot_id=int(robot_id),
                    order_date=parse_broker_order_date(
                        row.get("created_at") or row.get("createdTime") or row.get("updatedTime")
                    ),
                    commit=False,
                    promote_filled=True,
                    broker_prefix=broker_prefix
                )
                if result == "inserted":
                    imported += 1
                elif result == "updated":
                    upserted += 1

        try:
            self.db.commit()
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
        self.log.info(
            "    ↻ Заявки синхронизированы: imported=%s upserted=%s",
            imported,
            upserted
        )

    def _sync_daily_universe_from_portfolio(self, robot_id: int, portfolio_data: Dict[str, Any], snapshot_id: int) -> None:
        positions = list(portfolio_data.get("positions") or [])
        if not positions:
            return
        today = datetime.now(timezone.utc).date()
        insert_sql = text(
            f"""
            INSERT INTO daily_universe
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
            # Include shorts (negative qty) and longs; skip flat.
            if abs(qty) < 1e-12:
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
                    # FK daily_universe.snapshot_id -> market_snapshot.id.
                    # Portfolio snapshot id относится к другой таблице, поэтому не используем его здесь.
                    "snapshot_id": None,
                    "created_at": now,
                }
            )
        self.db.commit()

    def _handle_bybit_auth_failure(self, *, token_id: int, user_id: int, error: Exception) -> None:
        try:
            self._deactivate_token_and_disable_robots(
                token_id=token_id,
                user_id=user_id,
                error_message=str(error)
            )
            self.log.warning(
                "ByBit token expired/invalid -> deactivated token_id=%s and disabled robots for user_id=%s",
                token_id,
                user_id
            )
        except Exception as deact_exc:
            self.log.error(
                "Failed to deactivate ByBit token token_id=%s user_id=%s: %s",
                token_id,
                user_id,
                deact_exc
            )

    @staticmethod
    def _is_bybit_permission_error(exc: Exception) -> bool:
        """Account/endpoint ACL gap (key still valid for other wallets)."""
        if isinstance(exc, BybitApiError) and getattr(exc, "ret_code", None) == 10005:
            return True
        msg = str(exc or "").lower()
        return "permission denied" in msg or "retcode=10005" in msg

    @staticmethod
    def _is_bybit_auth_error(exc: Exception) -> bool:
        """True only for hard key death — not per-wallet permission gaps.

        ByBit 10005 (Permission denied) on FUND/COPY must NOT expire the token:
        UNIFIED can still work with the same key. Same for 10004 (sign) on a
        single endpoint — that is usually a request bug, not a revoked key.
        """
        if isinstance(exc, BybitApiError):
            if getattr(exc, "status_code", None) == 401:
                return True
            # 10003 invalid key, 10007 user auth failed / key restricted hard.
            if getattr(exc, "ret_code", None) in {10003, 10007}:
                return True
        msg = str(exc or "").lower()
        # Missing local api_secret is misconfig, not a revoked key.
        markers = (
            "invalid api key",
            "api key is invalid",
            "unauthorized",
            "retcode=10003",
            "retcode=10007"
        )
        return any(m in msg for m in markers)

    def _deactivate_token_and_disable_robots(self, *, token_id: int, user_id: int, error_message: str) -> None:
        now = datetime.now(timezone.utc)
        params = {
            "token_id": int(token_id),
            "user_id": int(user_id),
            "now": now,
            "error_message": str(error_message or "")[:500],
        }
        has_status = bool(self.db.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = :schema
                  AND table_name = 'api_tokens'
                  AND column_name = 'status'
                LIMIT 1
                """
            ),
            {"schema": settings.DB_SCHEMA}
        ).first())
        if has_status:
            self.db.execute(
                text(
                    f"""
                    UPDATE api_tokens
                    SET status = 3, updated_at = :now
                    WHERE id = :token_id AND user_id = :user_id
                    """
                ),
                params
            )
        self.db.execute(
            text(
                f"""
                UPDATE robots
                SET status = 2,
                    last_error = :error_message,
                    last_error_at = :now,
                    usermod = :user_id,
                    date_modification = :now
                WHERE token_id = :token_id
                  AND user_id = :user_id
                  AND status != 0
                """
            ),
            params
        )
        self.db.commit()
