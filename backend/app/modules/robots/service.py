# app/modules/robots/service.py
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
import math
import json

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

from app.modules.tinvest.token_service import token_service
from app.modules.tinvest.service import tinvest_service
from app.core.config import settings
from app.core.logging_config import get_logger
from . import queries, schemas
from app.modules.dictionary import queries as dict_queries

logger = get_logger(__name__)


class RobotService:
    """Сервис для управления торговыми роботами"""

    def __init__(self):
        self.db: Optional[Session] = None

    def _execute(self, query: str, params: dict, fetch_one: bool = False):
        """Утилита для выполнения запросов"""
        result = self.db.execute(text(query), params)
        return result.first() if fetch_one else result

    # === ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        """Безопасное преобразование в int"""
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        """Безопасное преобразование в float"""
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_str(value, default: str = '') -> str:
        """Безопасное преобразование в строку"""
        if value is None:
            return default
        return str(value)

    @staticmethod
    def _safe_bool(value, default: bool = False) -> bool:
        """Безопасное преобразование в bool"""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value == 1
        return bool(value)

    @staticmethod
    def _safe_datetime(value, default=None):
        """Безопасное преобразование в datetime"""
        return value if value is not None else default

    def _row_to_log_dict(self, row) -> dict:
        """Преобразует строку результата в словарь лога"""
        if not row or len(row) < 6:
            return {}

        return {
            "id": self._safe_int(row[0]),
            "robot_id": self._safe_int(row[1]),
            "level": self._safe_str(row[2]),
            "message": self._safe_str(row[3]),
            "details": row[4] if row[4] else None,
            "created_at": self._safe_datetime(row[5]),
        }

    # === УПРАВЛЕНИЕ РОБОТАМИ ===

    async def get_robot_by_id(
            self,
            db: Session,
            robot_id: int,
            user_id: int
    ) -> dict:
        """Получение робота по ID (с проверкой владельца)"""
        self.db = db

        query = queries.build_get_robot_by_id_query(schema=settings.DB_SCHEMA)
        result = db.execute(
            text(query),
            {"robot_id": robot_id, "user_id": user_id}
        ).first()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Робот не найден"
            )

        robot_dict = {
            "id": result[0],
            "user_id": result[1],
            "token":{
                "id": result[2],
                "name":result[3],
                "status":result[4],
                "type":result[5],
                "typeName": result[6]
            },
            "name": result[7],
            "type": result[8],
            "typeName": result[9],
            "status": result[10],
            "statusName": result[11],
            "config": result[12] or {},
            "schedule": None,
            "last_started": result[13],
            "last_error": result[14],
            "last_error_at": result[15],
            "last_stopped": result[16],
            "usercre": result[17],
            "date_creation": result[18],
            "usermod": result[19],
            "date_modification": result[20]
        }

        schedule_sql = f"""
            SELECT
                id, schedule_type, interval_seconds, start_time, end_time,
                weekdays, is_active, priority, description
            FROM {settings.DB_SCHEMA}.robot_schedules
            WHERE robot_id = :robot_id
              AND COALESCE(is_active, 1) = 1
            ORDER BY priority DESC, date_creation DESC
            LIMIT 1
        """
        schedule_row = db.execute(text(schedule_sql), {"robot_id": robot_id}).first()
        if schedule_row:
            robot_dict["schedule"] = {
                "id": int(schedule_row[0]),
                "schedule_type": schedule_row[1],
                "interval_seconds": schedule_row[2],
                "start_time": schedule_row[3],
                "end_time": schedule_row[4],
                "weekdays": schedule_row[5],
                "is_active": schedule_row[6],
                "priority": schedule_row[7],
                "description": schedule_row[8],
            }

        return robot_dict



    async def create_robot(
            self,
            db: Session,
            user_id: int,
            robot_data: schemas.RobotCreate
    ) -> dict:
        """Создание нового робота"""
        self.db = db

        # Проверяем уникальность имени
        check_name_query = queries.build_check_robot_name_exists_query(schema=settings.DB_SCHEMA)
        existing = db.execute(
            text(check_name_query),
            {"user_id": user_id, "name": robot_data.name}
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Робот с таким именем уже существует"
            )

        # Проверяем существование и активность токена
        check_token_query = queries.build_check_token_query(schema=settings.DB_SCHEMA)
        token = db.execute(
            text(check_token_query),
            {"token_id": robot_data.token_id, "user_id": user_id}
        ).first()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Токен не найден или не активен"
            )

        # Получаем тип робота из справочника
        robot_types = dict_queries.get_dictionary_data(
            db=db,
            table_name="ROBOT",
            column_name="TYPE",
            num_value=robot_data.type
        )

        if not robot_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Неверный тип робота: {robot_data.type}"
            )


        # Логика статуса:
        status_value = 2  # По умолчанию остановлен

        now = datetime.now(timezone.utc)

        # Создаем робота
        insert_query = queries.build_create_robot_query(schema=settings.DB_SCHEMA)
        result = db.execute(
            text(insert_query),
            {
                "user_id": user_id,
                "token_id": robot_data.token_id,
                "name": robot_data.name,
                "type": robot_data.type,
                "status": status_value,
                "usercre": user_id,
                "created_at": now
            }
        ).first()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать робота"
            )

        db.commit()

        # Получаем созданного робота с полной информацией
        robot = await self.get_robot_by_id(db, result[0], user_id)

        return robot

    async def update_robot(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            patch: schemas.RobotUpdate
    ) -> dict:
        """Обновляет базовые поля робота (name/token/type/status/config)."""
        self.db = db
        robot = await self.get_robot_by_id(db, robot_id, user_id)

        updates: Dict[str, Any] = {}
        if patch.name is not None:
            name = patch.name.strip()
            if not name:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название не может быть пустым")
            if name != robot.get("name"):
                check_name_query = queries.build_check_robot_name_exists_query(schema=settings.DB_SCHEMA)
                existing = db.execute(text(check_name_query), {"user_id": user_id, "name": name}).first()
                if existing and int(existing[0]) != int(robot_id):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Робот с таким именем уже существует")
            updates["name"] = name

        if patch.token_id is not None:
            check_token_query = queries.build_check_token_query(schema=settings.DB_SCHEMA)
            token = db.execute(text(check_token_query), {"token_id": patch.token_id, "user_id": user_id}).first()
            if not token:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен не найден или не активен")
            updates["token_id"] = int(patch.token_id)

        if patch.type is not None:
            if int(patch.type) not in (1, 2):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Поддерживаются только типы 1 и 2")
            updates["type"] = int(patch.type)

        if patch.status is not None:
            if int(patch.status) not in (1, 2):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Статус должен быть 1 или 2")
            updates["status"] = int(patch.status)

        if patch.config is not None:
            cfg = dict(patch.config)
            if int(updates.get("type", robot.get("type") or 0)) == 2:
                self._validate_robot_config(cfg)
            updates["config"] = json.dumps(cfg, ensure_ascii=False)

        set_parts = []
        params: Dict[str, Any] = {
            "robot_id": robot_id,
            "user_id": user_id,
            "usermod": user_id,
            "now": datetime.now(timezone.utc),
        }
        if updates:
            for key, value in updates.items():
                set_parts.append(f"{key} = :{key}")
                params[key] = value

            update_sql = f"""
                UPDATE {settings.DB_SCHEMA}.robots
                SET {", ".join(set_parts)},
                    usermod = :usermod,
                    date_modification = :now
                WHERE id = :robot_id AND user_id = :user_id AND status != 0
                RETURNING id
            """
            changed = db.execute(text(update_sql), params).first()
            if not changed:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось обновить робота")

        schedule_changed = any([
            patch.poll_interval_hours is not None,
            patch.trading_hours_start is not None,
            patch.trading_hours_end is not None,
            patch.allowed_weekdays is not None,
        ])
        if schedule_changed:
            existing_schedule = robot.get("schedule") or {}
            resolved_poll_hours = int(patch.poll_interval_hours if patch.poll_interval_hours is not None else max(1, round(float(existing_schedule.get("interval_seconds") or 3600) / 3600)))
            resolved_start = str(patch.trading_hours_start if patch.trading_hours_start is not None else "10:00")
            resolved_end = str(patch.trading_hours_end if patch.trading_hours_end is not None else "18:45")
            resolved_weekdays = int(patch.allowed_weekdays if patch.allowed_weekdays is not None else int(existing_schedule.get("weekdays") or 31))
            await self._replace_robot_schedule(
                db=db,
                robot_id=robot_id,
                user_id=user_id,
                poll_interval_hours=resolved_poll_hours,
                trading_hours_start=resolved_start,
                trading_hours_end=resolved_end,
                allowed_weekdays=resolved_weekdays,
            )
        db.commit()
        return await self.get_robot_by_id(db, robot_id, user_id)



# TODO: Добавить валидацию обязательноых полей для включения
#     Первый статус - наличие рефреш интервала
    async def change_robot_status(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            new_status: int  # 1 - включить, 2 - выключить
    ) -> dict:
        self.db = db
        robot = await self.get_robot_by_id(db, robot_id, user_id)

        if new_status == 1:
            token = robot.get("token", {})
            if not token.get("id") or token.get("status") != 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="У робота нет активного токена доступа"
                )

        now = datetime.now(timezone.utc)

        # Обновляем статус
        update_query = queries.build_change_robot_status_query(schema=settings.DB_SCHEMA)
        result = db.execute(
            text(update_query),
            {
                "robot_id": robot_id,
                "user_id": user_id,
                "status": new_status,
                "now": now,
                "usermod": user_id
            }
        ).first()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось изменить статус робота"
            )

        db.commit()

        # Получаем обновленного робота
        updated_robot = await self.get_robot_by_id(db, robot_id, user_id)

        return updated_robot

    async def delete_robot(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
    ) -> dict:
        """Мягкое удаление робота (status=0)"""
        self.db = db
        await self.get_robot_by_id(db, robot_id, user_id)

        now = datetime.now(timezone.utc)
        delete_query = queries.build_soft_delete_robot_query(schema=settings.DB_SCHEMA)
        result = db.execute(
            text(delete_query),
            {"robot_id": robot_id, "user_id": user_id, "usermod": user_id, "now": now}
        ).first()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось удалить робота"
            )
        db.commit()
        return {"id": result[0], "deleted": True}

    async def get_available_strategies(self) -> List[Dict[str, Any]]:
        """Возвращает список доступных стратегий и их схем параметров."""
        from app.modules.robots.trading.strategies import list_strategies
        return list_strategies()

    async def get_strategy_info(self, name: str) -> Dict[str, Any]:
        """Returns one strategy metadata by name."""
        from app.modules.robots.trading.strategies import get_strategy_info
        info = get_strategy_info(name)
        if not info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Стратегия '{name}' не найдена",
            )
        return info

    async def update_robot_config(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            config: Dict[str, Any]
    ) -> dict:
        """
        Обновляет конфиг робота с базовой валидацией strategy_params.
        """
        self.db = db
        robot = await self.get_robot_by_id(db, robot_id, user_id)
        robot_type = int(robot.get("type") or 0)
        if robot_type == 2:
            self._validate_robot_config(config)
        else:
            # Для опросника портфеля оставляем свободный JSON-конфиг.
            if not isinstance(config, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Некорректный config: expected object",
                )

        update_query = queries.build_update_robot_config_query(schema=settings.DB_SCHEMA)
        result = db.execute(
            text(update_query),
            {
                "robot_id": robot_id,
                "user_id": user_id,
                "config": json.dumps(config, ensure_ascii=False),
                "usermod": user_id,
                "now": datetime.now(timezone.utc)
            }
        ).first()
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить конфигурацию робота"
            )
        db.commit()
        return await self.get_robot_by_id(db, robot_id, user_id)

    async def update_robot_schedule(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            poll_interval_hours: int,
            trading_hours_start: str,
            trading_hours_end: str,
            allowed_weekdays: int,
    ) -> dict:
        """Обновляет/создает активное расписание в robot_schedules."""
        self.db = db
        await self.get_robot_by_id(db, robot_id, user_id)
        await self._replace_robot_schedule(
            db=db,
            robot_id=robot_id,
            user_id=user_id,
            poll_interval_hours=poll_interval_hours,
            trading_hours_start=trading_hours_start,
            trading_hours_end=trading_hours_end,
            allowed_weekdays=allowed_weekdays,
        )
        db.commit()
        return await self.get_robot_by_id(db, robot_id, user_id)

    async def _replace_robot_schedule(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            poll_interval_hours: int,
            trading_hours_start: str,
            trading_hours_end: str,
            allowed_weekdays: int,
    ) -> None:
        def _normalize_hhmm(hhmm: str) -> str:
            parts = (hhmm or "00:00").strip().split(":")
            h = int(parts[0]) if len(parts) > 0 else 0
            m = int(parts[1]) if len(parts) > 1 else 0
            h = max(0, min(23, h))
            m = max(0, min(59, m))
            return f"{h:02d}:{m:02d}:00+03:00"

        start_time_tz = _normalize_hhmm(trading_hours_start)
        end_time_tz = _normalize_hhmm(trading_hours_end)
        interval_seconds = int(max(1, min(12, poll_interval_hours)) * 3600)

        disable_sql = f"""
            UPDATE {settings.DB_SCHEMA}.robot_schedules
            SET is_active = 0,
                usermod = :usermod,
                date_modification = :now
            WHERE robot_id = :robot_id
              AND COALESCE(is_active, 1) = 1
        """
        db.execute(text(disable_sql), {"robot_id": robot_id, "usermod": user_id, "now": datetime.now(timezone.utc)})

        insert_sql = f"""
            INSERT INTO {settings.DB_SCHEMA}.robot_schedules
                (robot_id, schedule_type, interval_seconds, start_time, end_time, weekdays, is_active, priority, description, usercre, date_creation)
            VALUES
                (:robot_id, 2, :interval_seconds, CAST(:start_time AS timetz), CAST(:end_time AS timetz), :weekdays, 1, 100, :description, :usercre, :created_at)
        """
        db.execute(
            text(insert_sql),
            {
                "robot_id": robot_id,
                "interval_seconds": interval_seconds,
                "start_time": start_time_tz,
                "end_time": end_time_tz,
                "weekdays": int(max(0, min(127, allowed_weekdays))),
                "description": "UI schedule",
                "usercre": user_id,
                "created_at": datetime.now(timezone.utc),
            },
        )

    async def run_robot_history_backtest(
            self,
            db: Session,
            user_id: int,
            request: schemas.RobotHistoryBacktestRequest,
    ) -> Dict[str, Any]:
        """Исторический бэктест по конфигу робота: свечи из общей БД, дозагрузка через токен робота."""
        from app.modules.robots.trading.backtest.engine import run_backtest_simulation
        from app.modules.market_data import service as market_service

        robot = await self.get_robot_by_id(db, request.robot_id, user_id)
        if int(robot.get("type") or 0) != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Backtest доступен только для торговых роботов type=2",
            )
        token_id = robot["token"]["id"]
        token_row = await token_service.get_token_by_id(db, token_id, user_id)
        if not token_row or not token_row.get("token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Токен робота недоступен",
            )
        token = token_row["token"]
        config = robot.get("config") or {}
        figis: List[str] = list(config.get("allowed_figis") or (config.get("strategy_params") or {}).get("figis") or [])
        if not figis:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="В конфиге робота нет FIGI")

        strategy_name = config.get("strategy") or "grain_seed"
        strategy_params = dict(config.get("strategy_params") or {})
        strategy_params["figis"] = figis
        interval = strategy_params.get("interval", "CANDLE_INTERVAL_DAY")
        risk = dict(config.get("risk") or {})

        try:
            candles_by_figi: Dict[str, Any] = {}
            for figi in figis:
                await market_service.ensure_candles_cover_window(
                    db, figi, interval, request.from_date, request.to_date, token,
                )
                cl = market_service.load_candles_for_backtest(
                    db, figi, interval, request.from_date, request.to_date,
                )
                candles_by_figi[figi] = cl

            res = await run_backtest_simulation(
                candles_by_figi=candles_by_figi,
                strategy_name=strategy_name,
                strategy_params=strategy_params,
                risk_params=risk,
                initial_capital=request.initial_capital,
                robot_config_for_cost_defaults=config,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("robot history backtest failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Ошибка загрузки данных или расчёта: {e}",
            )

        result = {
            "initial_capital": res.initial_capital,
            "final_equity": res.final_equity,
            "total_return_percent": res.total_return_percent,
            "max_drawdown_percent": res.max_drawdown_percent,
            "trades": res.trades,
            "equity_curve": res.equity_curve,
        }
        try:
            save_sql = f"""
                INSERT INTO {settings.DB_SCHEMA}.robot_backtest_runs
                (robot_id, requested_from, requested_to, initial_capital, final_equity, total_return_percent, max_drawdown_percent, result_payload, created_at)
                VALUES
                (:robot_id, :requested_from, :requested_to, :initial_capital, :final_equity, :total_return_percent, :max_drawdown_percent, :result_payload, :created_at)
            """
            db.execute(
                text(save_sql),
                {
                    "robot_id": request.robot_id,
                    "requested_from": request.from_date,
                    "requested_to": request.to_date,
                    "initial_capital": res.initial_capital,
                    "final_equity": res.final_equity,
                    "total_return_percent": res.total_return_percent,
                    "max_drawdown_percent": res.max_drawdown_percent,
                    "result_payload": result,
                    "created_at": datetime.now(timezone.utc),
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("failed to persist robot backtest run")
        return result

    async def get_live_snapshot(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
    ) -> Dict[str, Any]:
        """REST snapshot для Live-экрана (на случай реконнекта/перезагрузки)."""
        robot = await self.get_robot_by_id(db, robot_id, user_id)
        if int(robot.get("type") or 0) != 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Робот не является торговым")

        config = dict(robot.get("config") or {})
        strategy = str(config.get("strategy") or "grain_seed")
        broker_type = str(config.get("broker_type") or "tinvest")
        account_id = config.get("account_id")

        positions_q = f"""
            SELECT id, figi, side, quantity, COALESCE(entry_price, price) AS entry_price, status, created_at
            FROM {settings.DB_SCHEMA}.robot_trades
            WHERE robot_id = :robot_id
              AND status IN ('open', 'partial')
            ORDER BY created_at DESC
            LIMIT 100
        """
        positions_rows = db.execute(text(positions_q), {"robot_id": robot_id}).fetchall()
        active_positions = [
            {
                "id": int(r[0]),
                "figi": str(r[1]),
                "side": str(r[2]),
                "quantity": float(r[3] or 0),
                "entry_price": float(r[4] or 0),
                "status": str(r[5]),
                "created_at": r[6],
            }
            for r in positions_rows
        ]

        signals_q = f"""
            SELECT id, figi, signal_type, signal_strength, price_at_signal, was_executed, created_at
            FROM {settings.DB_SCHEMA}.robot_signals
            WHERE robot_id = :robot_id
            ORDER BY created_at DESC
            LIMIT 100
        """
        signals_rows = db.execute(text(signals_q), {"robot_id": robot_id}).fetchall()
        recent_signals = [
            {
                "id": int(r[0]),
                "figi": str(r[1]),
                "signal_type": str(r[2]),
                "signal_strength": int(r[3] or 0),
                "price_at_signal": float(r[4] or 0),
                "was_executed": int(r[5] or 0),
                "created_at": r[6],
            }
            for r in signals_rows
        ]

        orders_q = f"""
            SELECT id, figi, side, quantity, price, order_id, status, created_at
            FROM {settings.DB_SCHEMA}.robot_trades
            WHERE robot_id = :robot_id
            ORDER BY created_at DESC
            LIMIT 100
        """
        orders_rows = db.execute(text(orders_q), {"robot_id": robot_id}).fetchall()
        recent_orders = [
            {
                "id": int(r[0]),
                "figi": str(r[1]),
                "side": str(r[2]),
                "quantity": float(r[3] or 0),
                "price": float(r[4] or 0),
                "order_id": r[5],
                "status": str(r[6]),
                "created_at": r[7],
            }
            for r in orders_rows
        ]

        stream_q = f"""
            SELECT MAX(created_at) AS last_event_at
            FROM {settings.DB_SCHEMA}.robot_execution_logs
            WHERE robot_id = :robot_id
        """
        stream_row = db.execute(text(stream_q), {"robot_id": robot_id}).first()
        stream_health = {
            "last_event_at": stream_row[0] if stream_row else None,
            "connected_hint": int(robot.get("status") or 0) == 1,
        }

        return {
            "robot_id": int(robot_id),
            "status": int(robot.get("status") or 0),
            "broker_type": broker_type,
            "strategy": strategy,
            "account_id": account_id,
            "active_positions": active_positions,
            "recent_signals": recent_signals,
            "recent_orders": recent_orders,
            "stream_health": stream_health,
        }

    async def get_backtest_history(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            limit: int = 30,
    ) -> Dict[str, Any]:
        await self.get_robot_by_id(db, robot_id, user_id)

        total_sql = f"""
            SELECT COUNT(*)
            FROM {settings.DB_SCHEMA}.robot_backtest_runs
            WHERE robot_id = :robot_id
        """
        total = int(db.execute(text(total_sql), {"robot_id": robot_id}).scalar() or 0)

        rows_sql = f"""
            SELECT id, robot_id, requested_from, requested_to, initial_capital, final_equity,
                   total_return_percent, max_drawdown_percent, created_at, result_payload
            FROM {settings.DB_SCHEMA}.robot_backtest_runs
            WHERE robot_id = :robot_id
            ORDER BY created_at DESC
            LIMIT :limit
        """
        rows = db.execute(text(rows_sql), {"robot_id": robot_id, "limit": limit}).fetchall()
        items = [
            {
                "id": int(r[0]),
                "robot_id": int(r[1]),
                "requested_from": r[2],
                "requested_to": r[3],
                "initial_capital": float(r[4] or 0),
                "final_equity": float(r[5] or 0),
                "total_return_percent": float(r[6] or 0),
                "max_drawdown_percent": float(r[7]) if r[7] is not None else None,
                "created_at": r[8],
                "result_payload": r[9] or {},
            }
            for r in rows
        ]
        return {"total": total, "items": items}

    async def run_backtest(self, request: schemas.BacktestRequest) -> Dict[str, Any]:
        returns = request.returns or []
        equity = float(request.initial_capital)
        equity_curve = [equity]
        fee_mult = float(request.fee_bps) / 10000.0

        for r in returns:
            pnl = equity * float(r)
            fees = abs(equity * float(r)) * fee_mult
            equity = max(0.0, equity + pnl - fees)
            equity_curve.append(equity)

        total_return_pct = ((equity / request.initial_capital) - 1.0) * 100.0 if request.initial_capital > 0 else 0.0
        max_dd = self._calc_drawdown_percent(equity_curve)
        sharpe = self._calc_sharpe_from_returns(returns)
        return {
            "initial_capital": round(request.initial_capital, 4),
            "final_equity": round(equity, 4),
            "total_return_percent": round(total_return_pct, 4),
            "max_drawdown_percent": round(max_dd, 4),
            "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
            "trades_count": len(returns),
            "equity_curve": [round(v, 4) for v in equity_curve],
        }

    async def run_walk_forward(self, request: schemas.WalkForwardRequest) -> Dict[str, Any]:
        returns = request.returns or []
        if len(returns) < request.folds * 4:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Недостаточно точек returns для walk-forward"
            )
        chunk = max(2, len(returns) // request.folds)
        folds = []
        for idx in range(request.folds):
            start = idx * chunk
            end = min(len(returns), start + chunk)
            segment = returns[start:end]
            if len(segment) < 2:
                continue
            train_len = max(1, int(len(segment) * request.train_ratio))
            test = segment[train_len:]
            if not test:
                continue
            bt = await self.run_backtest(
                schemas.BacktestRequest(
                    returns=test,
                    initial_capital=request.initial_capital,
                    fee_bps=request.fee_bps,
                )
            )
            folds.append({
                "fold": idx + 1,
                "train_points": train_len,
                "test_points": len(test),
                "final_equity": bt["final_equity"],
                "total_return_percent": bt["total_return_percent"],
                "max_drawdown_percent": bt["max_drawdown_percent"],
                "sharpe_ratio": bt["sharpe_ratio"],
            })
        if not folds:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Walk-forward не удалось построить")
        avg_return = sum(f["total_return_percent"] for f in folds) / len(folds)
        sharpes = [f["sharpe_ratio"] for f in folds if f.get("sharpe_ratio") is not None]
        avg_sharpe = (sum(sharpes) / len(sharpes)) if sharpes else None
        return {
            "folds": folds,
            "avg_total_return_percent": round(avg_return, 4),
            "avg_sharpe_ratio": round(avg_sharpe, 4) if avg_sharpe is not None else None,
        }

    async def set_paper_mode(self, db: Session, user_id: int, robot_id: int, enabled: bool) -> Dict[str, Any]:
        robot = await self.get_robot_by_id(db, robot_id, user_id)
        config = dict(robot.get("config") or {})
        config["paper_mode"] = bool(enabled)
        await self.update_robot_config(db, robot_id, user_id, config)
        return {"robot_id": robot_id, "paper_mode": bool(enabled)}

    @staticmethod
    def _calc_drawdown_percent(curve: List[float]) -> float:
        if not curve:
            return 0.0
        peak = curve[0]
        max_dd = 0.0
        for v in curve:
            peak = max(peak, v)
            if peak > 0:
                dd = ((peak - v) / peak) * 100.0
                max_dd = max(max_dd, dd)
        return max_dd

    @staticmethod
    def _calc_sharpe_from_returns(returns: List[float]) -> Optional[float]:
        if not returns:
            return None
        n = len(returns)
        mean = sum(float(r) for r in returns) / n
        if n < 2:
            return None
        var = sum((float(r) - mean) ** 2 for r in returns) / (n - 1)
        std = math.sqrt(var)
        if std <= 0:
            return None
        return (mean / std) * math.sqrt(n)

    def _validate_robot_config(self, config: Dict[str, Any]) -> None:
        """
        Валидирует конфигурацию grain_seed через pydantic-схему.
        """
        try:
            validated = schemas.GrainSeedConfig.model_validate(config)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Некорректный config: {e}",
            )

        supported_brokers = {"tinvest", "vtb", "alfa"}
        if str(validated.broker_type or "").lower() not in supported_brokers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"broker_type '{validated.broker_type}' не поддерживается",
            )

        config.clear()
        config.update(validated.model_dump())


# Создаем экземпляр сервиса
robot_service = RobotService()
