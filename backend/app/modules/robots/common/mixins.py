"""
Общие миксины для роботов
Устраняет дублирование кода между TradingRobot и TradingSession
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsCommonMixins [1]
#/// Исходный модуль `backend/app/modules/robots/common/mixins.py` — автоматическая разметка для Obsidian Source Scanner.

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy import text

from app.modules.robots.common.utils import safe_int, safe_str, safe_float, safe_bool, safe_json_dumps


class TradePersistenceMixin:
    """
    Миксин для сохранения сигналов и сделок в БД
    Используется в TradingRobot и TradingSession
    """

    async def save_signals(
            self,
            db,
            schema: str,
            robot_id: int,
            signals: List[Dict]
    ) -> List[int]:
        """
        Сохраняет сигналы в БД

        Args:
            db: Сессия БД
            schema: Схема БД
            robot_id: ID робота
            signals: Список сигналов с полями: figi, signal, price

        Returns:
            Список ID сохранённых сигналов
        """
        if not db or not signals:
            return []

        signal_ids = []

        for signal in signals:
            indicators = dict(signal.get("indicators") or {})
            if signal.get("target_price") is not None:
                indicators["target_price"] = signal.get("target_price")
            indicators_json = safe_json_dumps(indicators) if indicators else None
            query = f"""
                INSERT INTO {schema}.robot_signals
                (robot_id, figi, signal_type, signal_strength, price_at_signal,
                 indicators, was_executed, created_at)
                VALUES
                (:robot_id, :figi, :signal_type, :signal_strength, :price,
                 CAST(:indicators AS jsonb), 0, :now)
                RETURNING id
            """

            try:
                result = db.execute(
                    text(query),
                    {
                        "robot_id": robot_id,
                        "figi": signal["figi"],
                        "signal_type": signal["signal"].lower(),
                        "signal_strength": signal.get("strength", 100),
                        "price": signal["price"],
                        "indicators": indicators_json,
                        "now": datetime.now(timezone.utc)
                    }
                ).first()

                if result:
                    signal_id = result[0]
                    signal_ids.append(signal_id)
                    signal["_signal_id"] = signal_id

            except Exception as e:
                db.rollback()
                raise

        if signal_ids:
            db.commit()
            try:
                from app.modules.robots.live_events import notify_robot_live_event, uses_postgres_live_events
                if uses_postgres_live_events():
                    for sid in signal_ids:
                        notify_robot_live_event(db, robot_id, "signal", sid)
                    db.commit()
            except Exception:
                pass

        return signal_ids

    async def mark_signals_executed(
            self,
            db,
            schema: str,
            signal_ids: List[int],
            executed_trade_id: Optional[int] = None,
    ) -> int:
        """Marks signals as executed by ids."""
        if not db or not signal_ids:
            return 0
        try:
            query = f"""
                UPDATE {schema}.robot_signals
                SET was_executed = 1,
                    executed_trade_id = COALESCE(:executed_trade_id, executed_trade_id)
                WHERE id = :signal_id
            """
            for signal_id in signal_ids:
                db.execute(text(query), {"signal_id": signal_id, "executed_trade_id": executed_trade_id})
            db.commit()
            return len(signal_ids)
        except Exception:
            db.rollback()
            return 0

    async def save_trades(
            self,
            db,
            schema: str,
            robot_id: int,
            trades: List[Dict]
    ) -> List[int]:
        """
        Сохраняет сделки в БД

        Args:
            db: Сессия БД
            schema: Схема БД
            robot_id: ID робота
            trades: Список сделок с полями: figi, side, quantity, price, total_amount,
                    entry_price, commission, status, order_id

        Returns:
            Список ID сохранённых сделок
        """
        if not db or not trades:
            return []

        trade_ids = []

        for trade in trades:
            order_id = trade.get("order_id")
            oid = str(order_id).strip() if order_id is not None else ""
            is_broker_import = oid.startswith("broker_import:")

            if is_broker_import:
                from app.modules.robots.trading.broker_position_sync import (
                    legacy_broker_import_order_ids,
                )

                candidate_ids = legacy_broker_import_order_ids(
                    str(trade.get("figi") or ""),
                    str(trade.get("side") or ""),
                    robot_id=int(robot_id),
                )
                # Prefer exact id from payload first.
                if oid and oid not in candidate_ids:
                    candidate_ids = [oid, *candidate_ids]

                existing = db.execute(
                    text(
                        f"""
                        SELECT id, order_id
                        FROM {schema}.robot_trades
                        WHERE robot_id = :robot_id
                          AND order_id = ANY(:order_ids)
                        ORDER BY
                          CASE WHEN LOWER(COALESCE(status, '')) = 'open' THEN 0 ELSE 1 END,
                          id DESC
                        LIMIT 1
                        """
                    ),
                    {"robot_id": int(robot_id), "order_ids": candidate_ids},
                ).first()
                if existing:
                    trade_id = int(existing[0])
                    db.execute(
                        text(
                            f"""
                            UPDATE {schema}.robot_trades
                            SET status = :status,
                                figi = :figi,
                                side = :side,
                                quantity = :quantity,
                                price = :price,
                                total_amount = :total_amount,
                                entry_price = :entry_price,
                                commission = COALESCE(:commission, commission),
                                order_id = :order_id,
                                filled_quantity = :filled_quantity,
                                avg_fill_price = :avg_fill_price,
                                updated_at = :now
                            WHERE id = :id
                            """
                        ),
                        {
                            "id": trade_id,
                            "status": trade["status"],
                            "figi": trade["figi"],
                            "side": trade["side"],
                            "quantity": trade["quantity"],
                            "price": trade["price"],
                            "total_amount": trade["total_amount"],
                            "entry_price": trade.get("entry_price"),
                            "commission": trade.get("commission"),
                            "order_id": oid or candidate_ids[0],
                            "filled_quantity": trade.get("filled_quantity"),
                            "avg_fill_price": trade.get("avg_fill_price"),
                            "now": datetime.now(timezone.utc),
                        },
                    )
                    trade_ids.append(trade_id)
                    continue

            query = f"""
                INSERT INTO {schema}.robot_trades
                (robot_id, figi, side, quantity, price, total_amount,
                 entry_price, commission, status, order_id,
                 filled_quantity, avg_fill_price, created_at)
                VALUES
                (:robot_id, :figi, :side, :quantity, :price, :total_amount,
                 :entry_price, :commission, :status, :order_id,
                 :filled_quantity, :avg_fill_price, :now)
                RETURNING id
            """

            try:
                result = db.execute(
                    text(query),
                    {
                        "robot_id": robot_id,
                        "figi": trade["figi"],
                        "side": trade["side"],
                        "quantity": trade["quantity"],
                        "price": trade["price"],
                        "total_amount": trade["total_amount"],
                        "entry_price": trade.get("entry_price"),
                        "commission": trade.get("commission"),
                        "status": trade["status"],
                        "order_id": trade.get("order_id"),
                        "filled_quantity": trade.get("filled_quantity"),
                        "avg_fill_price": trade.get("avg_fill_price"),
                        "now": datetime.now(timezone.utc)
                    }
                ).first()

                if result:
                    trade_ids.append(result[0])

            except Exception:
                db.rollback()
                raise

        if trade_ids:
            db.commit()

        return trade_ids

    async def update_trade_status(
            self,
            db,
            schema: str,
            order_id: str,
            status: str,
            executed_price: Optional[float] = None,
            filled_quantity: Optional[int] = None,
            commission: Optional[float] = None,
            *,
            closing: bool = False,
    ) -> bool:
        """
        Обновляет статус сделки в БД

        Args:
            db: Сессия БД
            schema: Схема БД
            order_id: ID заявки
            status: Новый статус
            executed_price: Цена исполнения (если есть)
            filled_quantity: Исполненное количество (если есть)
            commission: Комиссия (если есть)
            closing: True for exit fills — mark closed; entry fills stay open

        Returns:
            True если обновление успешно
        """
        # Entry FILL = open position; exit FILL (closing=True) = closed.
        # NEW/resting → pending (distinct from open position after fill).
        fill_status = "closed" if closing else "open"
        status_mapping = {
            "EXECUTION_REPORT_STATUS_FILL": fill_status,
            "EXECUTION_REPORT_STATUS_PARTIALLYFILL": "partial",
            "EXECUTION_REPORT_STATUS_CANCELLED": "cancelled",
            "EXECUTION_REPORT_STATUS_REJECTED": "rejected",
            "EXECUTION_REPORT_STATUS_NEW": "pending",
        }
        db_status = status_mapping.get(status, status.lower())

        query = f"""
            UPDATE {schema}.robot_trades
            SET status = :status,
                filled_quantity = COALESCE(:filled_quantity, filled_quantity),
                avg_fill_price = COALESCE(:executed_price, avg_fill_price),
                commission = COALESCE(:commission, commission),
                updated_at = :now
            WHERE order_id = :order_id
        """

        try:
            db.execute(
                text(query),
                {
                    "order_id": order_id,
                    "status": db_status,
                    "filled_quantity": filled_quantity,
                    "executed_price": executed_price,
                    "commission": commission,
                    "now": datetime.now(timezone.utc)
                }
            )
            db.commit()

            # Если заявка полностью исполнена, обновляем entry_price
            if status == "EXECUTION_REPORT_STATUS_FILL" and executed_price:
                await self._update_trade_entry_price(
                    db, schema, order_id, executed_price, filled_quantity
                )

            return True

        except Exception as e:
            db.rollback()
            return False

    async def save_order_event(
            self,
            db,
            schema: str,
            robot_id: int,
            order_id: Optional[str],
            status: str,
            event_type: str = "status_update",
            trade_id: Optional[int] = None,
            payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        if not db:
            return None
        q = f"""
            INSERT INTO {schema}.robot_order_events
            (robot_id, trade_id, order_id, status, event_type, payload, created_at)
            VALUES
            (:robot_id, :trade_id, :order_id, :status, :event_type, CAST(:payload AS jsonb), :now)
            RETURNING id
        """
        payload_json = safe_json_dumps(payload) if payload is not None else None
        try:
            row = db.execute(
                text(q),
                {
                    "robot_id": robot_id,
                    "trade_id": trade_id,
                    "order_id": order_id,
                    "status": status,
                    "event_type": event_type,
                    "payload": payload_json,
                    "now": datetime.now(timezone.utc),
                }
            ).first()
            db.commit()
            event_id = row[0] if row else None
            if event_id is not None:
                try:
                    from app.modules.robots.live_events import (
                        notify_live_orders_refresh,
                        notify_robot_live_event,
                        uses_postgres_live_events,
                    )
                    if uses_postgres_live_events():
                        ws_type = "skipped" if str(status).strip().lower() == "skipped" else "order"
                        notify_robot_live_event(db, robot_id, ws_type, int(event_id))
                        db.commit()
                    if str(status).strip().lower() != "skipped":
                        notify_live_orders_refresh(int(robot_id))
                except Exception:
                    pass
            return event_id
        except Exception:
            db.rollback()
            raise

    async def save_decision(
            self,
            db,
            schema: str,
            robot_id: int,
            stage: str,
            decision_type: str,
            decision: str,
            reason_code: Optional[str] = None,
            payload: Optional[Dict[str, Any]] = None,
            execution_log_id: Optional[int] = None,
            cycle_id: Optional[int] = None,
            figi: Optional[str] = None,
    ) -> Optional[int]:
        if not db:
            return None
        q = f"""
            INSERT INTO {schema}.robot_decisions
            (robot_id, execution_log_id, cycle_id, figi, stage, decision_type, decision, reason_code, payload, created_at)
            VALUES
            (:robot_id, :execution_log_id, :cycle_id, :figi, :stage, :decision_type, :decision, :reason_code, CAST(:payload AS jsonb), :now)
            RETURNING id
        """
        payload_json = safe_json_dumps(payload) if payload is not None else None
        try:
            row = db.execute(
                text(q),
                {
                    "robot_id": robot_id,
                    "execution_log_id": execution_log_id,
                    "cycle_id": cycle_id,
                    "figi": figi,
                    "stage": stage,
                    "decision_type": decision_type,
                    "decision": decision,
                    "reason_code": reason_code,
                    "payload": payload_json,
                    "now": datetime.now(timezone.utc),
                }
            ).first()
            db.commit()
            return row[0] if row else None
        except Exception:
            db.rollback()
            raise

    async def create_run_cycle(
            self,
            db,
            schema: str,
            robot_id: int,
            execution_log_id: Optional[int] = None,
            context: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        if not db:
            return None
        q = f"""
            INSERT INTO {schema}.robot_run_cycles
            (robot_id, execution_log_id, status, started_at, context)
            VALUES
            (:robot_id, :execution_log_id, 'running', :started_at, CAST(:context AS jsonb))
            RETURNING id
        """
        context_json = safe_json_dumps(context) if context is not None else None
        try:
            row = db.execute(
                text(q),
                {
                    "robot_id": robot_id,
                    "execution_log_id": execution_log_id,
                    "started_at": datetime.now(timezone.utc),
                    "context": context_json,
                }
            ).first()
            db.commit()
            return row[0] if row else None
        except Exception:
            db.rollback()
            raise

    async def complete_run_cycle(
            self,
            db,
            schema: str,
            cycle_id: int,
            status: str = "completed",
            context: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not db:
            return
        q = f"""
            UPDATE {schema}.robot_run_cycles
            SET status = :status,
                finished_at = :finished_at,
                context = COALESCE(CAST(:context AS jsonb), context)
            WHERE id = :cycle_id
        """
        context_json = safe_json_dumps(context) if context is not None else None
        try:
            db.execute(
                text(q),
                {
                    "cycle_id": cycle_id,
                    "status": status,
                    "finished_at": datetime.now(timezone.utc),
                    "context": context_json,
                }
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

    async def _update_trade_entry_price(
            self,
            db,
            schema: str,
            order_id: str,
            executed_price: float,
            filled_quantity: int
    ):
        """Обновляет цену входа и количество для полностью исполненной заявки"""
        query = f"""
            UPDATE {schema}.robot_trades
            SET entry_price = :entry_price,
                quantity = :quantity,
                total_amount = :total_amount,
                status = 'open'
            WHERE order_id = :order_id AND status IN ('pending', 'partial', 'open')
        """

        db.execute(
            text(query),
            {
                "order_id": order_id,
                "entry_price": executed_price,
                "quantity": filled_quantity,
                "total_amount": executed_price * filled_quantity
            }
        )
        db.commit()


class PriceParsingMixin:
    """Миксин для парсинга цен из T-Invest формата (units/nano)"""

    @staticmethod
    def parse_price(price_data) -> Optional[float]:
        """
        Парсит цену: T-Invest Quotation `{units, nano}` или число (ByBit float).

        Returns:
            Цена в виде float или None
        """
        if price_data is None:
            return None
        if isinstance(price_data, (int, float)):
            v = float(price_data)
            return v if v > 0 else None
        if isinstance(price_data, str):
            try:
                v = float(price_data)
                return v if v > 0 else None
            except (TypeError, ValueError):
                return None
        if not isinstance(price_data, dict):
            return None

        units = price_data.get("units", 0)
        nano = price_data.get("nano", 0)

        try:
            units = int(units) if units else 0
            nano = int(nano) if nano else 0
        except (TypeError, ValueError):
            return None

        v = units + nano / 1e9
        return v if v > 0 else None

    @staticmethod
    def parse_money_value(money_value: dict) -> Optional[Dict[str, Any]]:
        """
        Парсит MoneyValue из T-Invest API

        Returns:
            Словарь с currency, units, nano, decimal
        """
        if not money_value:
            return None

        units = safe_int(money_value.get("units", 0))
        nano = money_value.get("nano", 0)
        decimal_value = units + nano / 1e9

        return {
            "currency": safe_str(money_value.get("currency", "RUB")).upper(),
            "units": units,
            "nano": nano,
            "decimal": round(decimal_value, 2)
        }

    @staticmethod
    def parse_quotation(quotation: dict) -> Optional[Dict[str, Any]]:
        """
        Парсит Quotation из T-Invest API

        Returns:
            Словарь с units, nano, decimal
        """
        if not quotation:
            return None

        units = safe_int(quotation.get("units", 0))
        nano = quotation.get("nano", 0)
        decimal_value = units + nano / 1e9

        return {
            "units": units,
            "nano": nano,
            "decimal": round(decimal_value, 4)
        }