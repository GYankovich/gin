# app/modules/robots/service.py
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta, date, time
import json
import httpx
import asyncio

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

    @staticmethod
    def _safe_float_opt(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int_opt(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dt_date_utc(v: datetime) -> date:
        if v.tzinfo:
            return v.astimezone(timezone.utc).date()
        return v.date()

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
            current_cfg = dict(robot.get("config") or {})
            incoming_cfg = dict(patch.config)
            cfg = {**current_cfg, **incoming_cfg}
            if "pipeline" in incoming_cfg:
                cfg["pipeline"] = incoming_cfg.get("pipeline")
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
            resolved_poll_hours = float(
                patch.poll_interval_hours
                if patch.poll_interval_hours is not None
                else max((1 / 60), float(existing_schedule.get("interval_seconds") or 3600) / 3600.0)
            )
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
            poll_interval_hours: float,
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
            poll_interval_hours: float,
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
        normalized_hours = max((1 / 60), min(12.0, float(poll_interval_hours)))
        interval_seconds = int(round(normalized_hours * 3600))
        interval_seconds = max(60, interval_seconds)

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

    @staticmethod
    def _iter_trade_dates(from_dt: datetime, to_dt: datetime) -> List[date]:
        d0 = from_dt.date()
        d1 = to_dt.date()
        out: List[date] = []
        cur = d0
        while cur <= d1:
            if cur.weekday() < 5:
                out.append(cur)
            cur += timedelta(days=1)
        return out

    @staticmethod
    def _iter_calendar_dates(from_dt: datetime, to_dt: datetime) -> List[date]:
        d0 = from_dt.date()
        d1 = to_dt.date()
        out: List[date] = []
        cur = d0
        while cur <= d1:
            out.append(cur)
            cur += timedelta(days=1)
        return out

    async def _fetch_moex_history_snapshot_day(
            self,
            *,
            day: date,
            board: str = "TQBR",
    ) -> List[Dict[str, Any]]:
        url = f"https://iss.moex.com/iss/history/engines/stock/markets/shares/boards/{board}/securities.json"
        out: List[Dict[str, Any]] = []
        start = 0
        page_size = 100
        max_pages = 50
        seen_signatures: set[str] = set()
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=8.0, read=20.0, write=20.0, pool=20.0), verify=False) as client:
            for _ in range(max_pages):
                params = {"iss.meta": "off", "date": day.isoformat(), "start": start}
                logger.info("moex history request day=%s board=%s start=%s", day.isoformat(), board, start)
                attempts = 3
                resp: Optional[httpx.Response] = None
                for attempt in range(1, attempts + 1):
                    try:
                        resp = await client.get(url, params=params)
                        break
                    except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.NetworkError) as e:
                        logger.warning(
                            "moex history fetch temporary failure day=%s board=%s start=%s attempt=%s/%s err=%s",
                            day.isoformat(),
                            board,
                            start,
                            attempt,
                            attempts,
                            str(e),
                        )
                        if attempt >= attempts:
                            return out
                        await asyncio.sleep(0.6 * attempt)
                    except Exception:
                        logger.exception("moex history fetch failed unexpectedly day=%s board=%s start=%s", day.isoformat(), board, start)
                        return out
                if resp is None or resp.status_code != 200:
                    break

                payload = resp.json() if resp.content else {}
                block = payload.get("history") or {}
                cols = block.get("columns") or []
                rows = block.get("data") or []
                if not rows:
                    logger.info("moex history empty page day=%s board=%s start=%s", day.isoformat(), board, start)
                    break

                sig = f"{start}:{len(rows)}:{rows[0][0] if rows and rows[0] else ''}:{rows[-1][0] if rows and rows[-1] else ''}"
                if sig in seen_signatures:
                    break
                seen_signatures.add(sig)

                idx = {c: i for i, c in enumerate(cols)}
                for r in rows:
                    secid_i = idx.get("SECID")
                    if secid_i is None or secid_i >= len(r):
                        continue

                    def g(name: str):
                        i = idx.get(name)
                        return r[i] if i is not None and i < len(r) else None

                    def g_first(*names: str):
                        for nm in names:
                            v = g(nm)
                            if v is not None:
                                return v
                        return None

                    close_price = self._safe_float_opt(g_first("LEGALCLOSEPRICE", "CLOSE"))
                    bid_price = self._safe_float_opt(g_first("BID", "BIDPRICE"))
                    ask_price = self._safe_float_opt(g_first("OFFER", "ASK", "ASKPRICE"))
                    spread_val = self._safe_float_opt(g_first("SPREAD"))
                    if spread_val is None and bid_price is not None and ask_price is not None:
                        spread_val = ask_price - bid_price
                    out.append({
                        "ticker": str(g("SECID") or "").upper(),
                        "board_id": g("BOARDID"),
                        "last_price": close_price,
                        "open_price": self._safe_float_opt(g("OPEN")),
                        "high_price": self._safe_float_opt(g("HIGH")),
                        "low_price": self._safe_float_opt(g("LOW")),
                        "prev_price": close_price,
                        "value_today": self._safe_float_opt(g("VALUE")),
                        "volume_lots": self._safe_float_opt(g("VOLUME")),
                        "num_trades": self._safe_int_opt(g("NUMTRADES")),
                        "short_name": g("SHORTNAME"),
                        "security_status": str(g_first("STATUS", "SECSTATUS", "SECURITYSTATUS") or "A"),
                        "trading_status": str(g_first("TRADINGSTATUS", "TRADING_STATUS") or "T"),
                        "issue_size": self._safe_float_opt(g_first("ISSUE_SIZE", "ISSUESIZE")),
                        "min_step": self._safe_float_opt(g_first("MINSTEP", "MIN_STEP")),
                        "bid": bid_price,
                        "ask": ask_price,
                        "spread": spread_val,
                        "raw_payload": {k: g(k) for k in cols},
                    })

                if len(rows) < page_size:
                    break
                start += page_size
        logger.info("moex history loaded day=%s board=%s rows=%s", day.isoformat(), board, len(out))
        return out

    async def _ensure_daily_snapshot_history(
            self,
            db: Session,
            *,
            day: date,
            board: str = "TQBR",
    ) -> Optional[int]:
        schema = settings.DB_SCHEMA
        min_rows_for_reuse = 150 if str(board).upper() == "TQBR" else 1
        day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        day_end_exclusive = day_start + timedelta(days=1)

        existing = db.execute(
            text(
                f"""
                SELECT h.id,
                       (
                           SELECT COUNT(*)
                           FROM {schema}.market_snapshot_data_history d
                           WHERE d.snapshot_id = h.id
                       ) AS data_rows
                FROM {schema}.market_snapshot_history h
                WHERE h.board=:board
                  AND h.status='SUCCESS'
                  AND h.snapshot_time >= :day_start
                  AND h.snapshot_time < :day_end
                ORDER BY h.snapshot_time ASC
                LIMIT 1
                """
            ),
            {"board": board, "day_start": day_start, "day_end": day_end_exclusive},
        ).first()
        existing_id = int(existing[0]) if existing else None
        existing_rows = int(existing[1] or 0) if existing else 0
        if existing_id and existing_rows >= min_rows_for_reuse:
            return existing_id
        if existing_id:
            db.execute(text(f"DELETE FROM {schema}.market_snapshot_data_history WHERE snapshot_id=:sid"), {"sid": existing_id})
            db.execute(text(f"DELETE FROM {schema}.market_snapshot_history WHERE id=:sid"), {"sid": existing_id})
            db.commit()

        rows = await self._fetch_moex_history_snapshot_day(day=day, board=board)
        if not rows:
            return None

        def _next_pk(table_name: str) -> int:
            seq_name = db.execute(
                text("SELECT pg_get_serial_sequence(:tbl, 'id')"),
                {"tbl": f"{schema}.{table_name}"},
            ).scalar()
            if seq_name:
                try:
                    return int(db.execute(text("SELECT nextval(:seq)"), {"seq": seq_name}).scalar())
                except Exception:
                    pass
            mx = db.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {schema}.{table_name}")).scalar()
            return int(mx or 0) + 1

        snapshot_id = _next_pk("market_snapshot_history")
        now_utc = datetime.now(timezone.utc)
        db.execute(
            text(
                f"""
                INSERT INTO {schema}.market_snapshot_history
                (id, snapshot_time, board, status, is_manual, ttl_minutes, created_at)
                VALUES
                (:id, :snapshot_time, :board, 'SUCCESS', TRUE, 0, :created_at)
                """
            ),
            {
                "id": snapshot_id,
                "snapshot_time": day_start,
                "board": board,
                "created_at": now_utc,
            },
        )

        next_data_id = _next_pk("market_snapshot_data_history")
        for i, r in enumerate(rows):
            rid = next_data_id + i
            raw = dict(r.get("raw_payload") or {})
            db.execute(
                text(
                    f"""
                    INSERT INTO {schema}.market_snapshot_data_history
                    (id, snapshot_id, ticker, last_price, open_price, prev_price, volume_today, value_today, volume_lots,
                     bid, ask, spread, security_status, trading_status, num_trades, min_step, issue_size, board_id,
                     short_name, low_price, high_price, securities_payload, marketdata_payload)
                    VALUES
                    (:id, :snapshot_id, :ticker, :last_price, :open_price, :prev_price, :volume_today, :value_today, :volume_lots,
                     :bid, :ask, :spread, :security_status, :trading_status, :num_trades, :min_step, :issue_size, :board_id,
                     :short_name, :low_price, :high_price, CAST(:securities_payload AS jsonb), CAST(:marketdata_payload AS jsonb))
                    """
                ),
                {
                    "id": rid,
                    "snapshot_id": snapshot_id,
                    "ticker": str(r.get("ticker") or "").upper(),
                    "last_price": r.get("last_price"),
                    "open_price": r.get("open_price"),
                    "prev_price": r.get("prev_price"),
                    "volume_today": r.get("volume_lots"),
                    "value_today": r.get("value_today"),
                    "volume_lots": r.get("volume_lots"),
                    "bid": r.get("bid"),
                    "ask": r.get("ask"),
                    "spread": r.get("spread"),
                    "security_status": r.get("security_status"),
                    "trading_status": r.get("trading_status"),
                    "num_trades": r.get("num_trades"),
                    "min_step": r.get("min_step"),
                    "issue_size": r.get("issue_size"),
                    "board_id": r.get("board_id"),
                    "short_name": r.get("short_name"),
                    "low_price": r.get("low_price"),
                    "high_price": r.get("high_price"),
                    "securities_payload": json.dumps(raw, ensure_ascii=False),
                    "marketdata_payload": json.dumps(raw, ensure_ascii=False),
                },
            )
        db.commit()
        return snapshot_id

    #///EPIC Backtesting.ITEM HistoryBacktest.TOPIC Endpoint Lifecycle [1]
    #/// Оркестрация /api/robots/history-backtest: merge config, подготовка history,
    #/// отбор тикеров через pipeline, загрузка свечей из cache/MOEX, симуляция и persist.
    #/// Источники данных приоритетно локальные таблицы ganaly/backtest, затем внешние API.
    async def run_robot_history_backtest(
            self,
            db: Session,
            user_id: int,
            request: schemas.RobotHistoryBacktestRequest,
    ) -> Dict[str, Any]:
        """Исторический бэктест: history-таблицы -> MOEX History API, затем симуляция."""
        from app.modules.robots.trading.backtest.engine import run_backtest_simulation
        from app.modules.robots.trading.backtest.persistence import BacktestPersistence, BacktestPersistPayload
        from app.modules.robots.trading.backtest.metrics import BacktestMetricsCalculator
        from app.modules.dms.service import dms_service

        robot = await self.get_robot_by_id(db, request.robot_id, user_id)
        if int(robot.get("type") or 0) != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Backtest доступен только для торговых роботов type=2",
            )

        config = dict(robot.get("config") or {})
        request_cfg = dict(request.config or {})
        if request_cfg:
            # Accept UI alias riskManagment and normalize to backend "risk".
            rm = request_cfg.pop("riskManagment", None)
            if isinstance(rm, dict):
                risk_alias: Dict[str, Any] = {}
                if rm.get("стопЛосс") is not None:
                    risk_alias["stop_loss_percent"] = rm.get("стопЛосс")
                if rm.get("тейкПрофит") is not None:
                    risk_alias["take_profit_percent"] = rm.get("тейкПрофит")
                if rm.get("доляПозиции") is not None:
                    risk_alias["max_position_percent"] = rm.get("доляПозиции")
                if rm.get("максПозиция") is not None:
                    risk_alias["max_position_rub"] = rm.get("максПозиция")
                request_cfg["risk"] = {**dict(request_cfg.get("risk") or {}), **risk_alias}
            config = {**config, **request_cfg}
            if isinstance(config.get("pipeline"), dict):
                config["pipeline"] = {**dict((robot.get("config") or {}).get("pipeline") or {}), **dict(config.get("pipeline") or {})}
            if isinstance(config.get("costs"), dict):
                config["costs"] = {**dict((robot.get("config") or {}).get("costs") or {}), **dict(config.get("costs") or {})}
            if isinstance(config.get("risk"), dict):
                config["risk"] = {**dict((robot.get("config") or {}).get("risk") or {}), **dict(config.get("risk") or {})}
            if isinstance(config.get("strategy_params"), dict):
                config["strategy_params"] = {**dict((robot.get("config") or {}).get("strategy_params") or {}), **dict(config.get("strategy_params") or {})}
        pipeline_filters = list((config.get("pipeline") or {}).get("filters") or [])
        fast_pipeline_filters = [
            f for f in pipeline_filters
            if str((f or {}).get("type") or "").lower() not in {"atr", "turnover", "min_step_ratio"}
        ]
        strategy_name = config.get("strategy") or "grain_seed"
        strategy_params = dict(config.get("strategy_params") or {})
        interval = str(strategy_params.get("interval", "CANDLE_INTERVAL_10_MIN") or "CANDLE_INTERVAL_10_MIN")
        interval_u = interval.upper()
        if any(token in interval_u for token in ("10_MIN", "INTERVAL_10", "I10", "10M", "10_MINUTE")):
            interval_code_num = 10
        elif any(token in interval_u for token in ("5_MIN", "INTERVAL_5", "M5", "5M", "5_MINUTE")):
            interval_code_num = 5
        elif any(token in interval_u for token in ("1_MIN", "INTERVAL_1", " I1", "I1", "1_MINUTE")):
            interval_code_num = 1
        elif any(token in interval_u for token in ("60_MIN", "HOUR", "INTERVAL_60", "I60", "1H", "60M")):
            interval_code_num = 60
        elif any(token in interval_u for token in ("WEEK", "INTERVAL_7", "I7", "1W")):
            interval_code_num = 7
        elif any(token in interval_u for token in ("MONTH", "INTERVAL_31", "I31")):
            interval_code_num = 31
        elif any(token in interval_u for token in ("QUARTER", "INTERVAL_4", "I4", "1Q", "1K")):
            interval_code_num = 4
        elif any(token in interval_u for token in ("DAY", "D1", "INTERVAL_24", "I24", "24")):
            interval_code_num = 24
        else:
            interval_code_num = 10
        interval_code = dms_service._interval_code_to_cache_label(interval_code_num)
        risk = dict(config.get("risk") or {})
        board = "TQBR"
        exec_cfg = dict(config.get("execution_model") or {})
        slippage_pct = float((exec_cfg.get("slippage_pct")) or 0.0)
        execution_model = str(exec_cfg.get("model") or "NEXT_BAR_OPEN").upper()

        stage_logs: List[str] = []
        pipeline_mode = str((config.get("pipeline") or {}).get("mode") or "ALL").upper()
        run_id = db.execute(
            text(f"""
                INSERT INTO {settings.DB_SCHEMA}.backtest_runs
                (robot_id, requested_from, requested_to, started_at, status, board, initial_capital, config_snapshot, execution_model)
                VALUES (:robot_id, :requested_from, :requested_to, :started_at, 'RUNNING', :board, :initial_capital, CAST(:config_snapshot AS jsonb), CAST(:execution_model AS jsonb))
                RETURNING id
            """),
            {
                "robot_id": request.robot_id,
                "requested_from": request.from_date,
                "requested_to": request.to_date,
                "started_at": datetime.now(timezone.utc),
                "board": board,
                "initial_capital": request.initial_capital,
                "config_snapshot": json.dumps(config, ensure_ascii=False),
                "execution_model": json.dumps({
                    "slippage_pct": slippage_pct,
                    "commission_model": "robot_costs",
                    "source_priority": [
                        "shared_market_candles",
                        "market_snapshot_history",
                        "market_snapshot_data_history",
                        "moex_iss_history_api",
                        "candles_cache",
                        "moex_iss_candles_api",
                    ],
                }, ensure_ascii=False),
            },
        ).scalar()
        db.commit()
        bt_run_id: Optional[int] = None

        try:
            stage_logs.append("init: created run")
            db.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {settings.DB_SCHEMA}.backtest_decisions (
                        id BIGSERIAL PRIMARY KEY,
                        run_id BIGINT NOT NULL REFERENCES {settings.DB_SCHEMA}.backtest_runs(id) ON DELETE CASCADE,
                        trade_date DATE NOT NULL,
                        ticker VARCHAR(20) NOT NULL,
                        source VARCHAR(20) NOT NULL DEFAULT 'PIPELINE',
                        result VARCHAR(20) NOT NULL,
                        reason TEXT NULL,
                        payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
            db.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_backtest_decisions_run_day
                    ON {settings.DB_SCHEMA}.backtest_decisions(run_id, trade_date)
                    """
                )
            )
            db.commit()
            try:
                bt_run_id = int(
                    db.execute(
                        text(
                            """
                            INSERT INTO backtest.backtest_runs
                            (name, description, robot_config_id, robot_config_snapshot, date_from, date_to, initial_capital,
                             commission_percent, slippage_percent, lot_fixed_fee, execution_model, status, progress_percent,
                             started_at, created_by)
                            VALUES
                            (:name, :description, :robot_config_id, CAST(:robot_config_snapshot AS jsonb), :date_from, :date_to, :initial_capital,
                             :commission_percent, :slippage_percent, :lot_fixed_fee, :execution_model, 'RUNNING', 0,
                             :started_at, :created_by)
                            RETURNING id
                            """
                        ),
                        {
                            "name": f"robot-{request.robot_id}-history-backtest",
                            "description": "Auto-created from /api/robots/history-backtest",
                            "robot_config_id": request.robot_id,
                            "robot_config_snapshot": json.dumps(config, ensure_ascii=False),
                            "date_from": self._dt_date_utc(request.from_date),
                            "date_to": self._dt_date_utc(request.to_date),
                            "initial_capital": request.initial_capital,
                            "commission_percent": float((config.get("costs") or {}).get("broker_commission_rate") or 0.0005) * 100.0,
                            "slippage_percent": slippage_pct,
                            "lot_fixed_fee": 0.0,
                            "execution_model": execution_model,
                            "started_at": datetime.now(timezone.utc),
                            "created_by": str(user_id),
                        },
                    ).scalar()
                    or 0
                )
                db.commit()
            except Exception:
                db.rollback()
                bt_run_id = None
            trade_dates = self._iter_calendar_dates(request.from_date, request.to_date)
            stage_logs.append(f"history: processing {len(trade_dates)} calendar dates")
            selected_tickers: List[str] = []
            history_tickers_all: set[str] = set()
            ensured_intraday_tickers: set[str] = set()
            allowed_figis_by_date: Dict[str, List[str]] = {}
            decisions_rows: List[Dict[str, Any]] = []
            day_stats: Dict[str, Dict[str, int]] = {}
            processed_days = 0
            skipped_fetch_days = 0
            skipped_empty_days = 0
            last_history_error: Optional[str] = None
            missing_history_days: List[str] = []
            for d in trade_dates:
                day_selected_tickers: set[str] = set()
                day_rows: List[Dict[str, Any]] = []
                fast_passed_rows: List[Dict[str, Any]] = []
                try:
                    snapshot_id = await self._ensure_daily_snapshot_history(db, day=d, board=board)
                except Exception as e:
                    logger.warning("history snapshot day skipped due to error day=%s err=%s", d.isoformat(), str(e))
                    last_history_error = str(e)
                    stage_logs.append(f"history: {d.isoformat()} skipped (fetch error: {str(e)})")
                    skipped_fetch_days += 1
                    missing_history_days.append(d.isoformat())
                    continue
                if not snapshot_id:
                    stage_logs.append(f"history: {d.isoformat()} skipped (no snapshot)")
                    skipped_empty_days += 1
                    missing_history_days.append(d.isoformat())
                    continue
                snap_time = db.execute(
                    text(f"SELECT snapshot_time FROM {settings.DB_SCHEMA}.market_snapshot_history WHERE id=:snapshot_id"),
                    {"snapshot_id": snapshot_id},
                ).scalar()
                try:
                    if snap_time and getattr(snap_time, "date", None) and snap_time.date() != d:
                        stage_logs.append(
                            f"history: {d.isoformat()} fallback to previous snapshot {snap_time.date().isoformat()}"
                        )
                except Exception:
                    pass
                processed_days += 1
                rows = db.execute(
                    text(f"""
                        SELECT ticker, last_price, open_price, high_price, low_price, prev_price, value_today, volume_lots, bid, ask, spread,
                               security_status, trading_status, num_trades, issue_size, min_step, securities_payload
                        FROM {settings.DB_SCHEMA}.market_snapshot_data_history
                        WHERE snapshot_id = :snapshot_id
                    """),
                    {"snapshot_id": snapshot_id},
                ).mappings().all()
                if not rows:
                    continue
                day_key = d.isoformat()
                day_stats[day_key] = {
                    "rows_total": len(rows),
                    "fast_passed": 0,
                    "final_passed": 0,
                }
                for r in rows:
                    row = dict(r)
                    day_rows.append(row)
                    ticker = str(row.get("ticker") or "").upper()
                    if ticker:
                        history_tickers_all.add(ticker)
                    eval_res = dms_service._evaluate_pipeline_row(
                        row,
                        fast_pipeline_filters,
                        pipeline_mode,
                        allow_missing_spread=True,
                    )
                    if bool(eval_res.get("accepted")) and ticker:
                        fast_passed_rows.append(row)
                        day_stats[day_key]["fast_passed"] += 1
                    else:
                        decisions_rows.append(
                            {
                                "trade_date": d.isoformat(),
                                "ticker": ticker,
                                "result": "REJECT",
                                "reason": eval_res.get("reason") or "fast_filter_reject",
                                "payload": {"stage": "fast", "eval": eval_res},
                            }
                        )
                # ATR/D1 cache only for fast-pass candidates, then final filtering with full pipeline.
                if fast_passed_rows:
                    atr_map, day_cache_stats = await dms_service._load_atr_percent_map(
                        db=db,
                        board=board,
                        rows=fast_passed_rows,
                        filters=pipeline_filters,
                        as_of_date=d,
                        fetch_missing_candles=False,
                        user_id=user_id,
                    )
                    if day_cache_stats.get("fetched_tickers"):
                        stage_logs.append(
                            f"candles(d1): {d.isoformat()} fetched_tickers={day_cache_stats.get('fetched_tickers', 0)} fetched_candles={day_cache_stats.get('fetched_candles', 0)}"
                        )
                    for fr in fast_passed_rows:
                        tk = str(fr.get("ticker") or "").upper()
                        if not tk:
                            continue
                        enriched = dict(fr)
                        if tk in atr_map:
                            enriched["atr_percent"] = atr_map[tk]
                        final_eval = dms_service._evaluate_pipeline_row(
                            enriched,
                            pipeline_filters,
                            pipeline_mode,
                            allow_missing_spread=True,
                        )
                        if bool(final_eval.get("accepted")):
                            selected_tickers.append(tk)
                            day_selected_tickers.add(tk)
                            day_stats[day_key]["final_passed"] += 1
                            decisions_rows.append(
                                {
                                    "trade_date": d.isoformat(),
                                    "ticker": tk,
                                    "result": "ACCEPT",
                                    "reason": None,
                                    "payload": {"stage": "final", "eval": final_eval},
                                }
                            )
                        else:
                            decisions_rows.append(
                                {
                                    "trade_date": d.isoformat(),
                                    "ticker": tk,
                                    "result": "REJECT",
                                    "reason": final_eval.get("reason") or "final_filter_reject",
                                    "payload": {"stage": "final", "eval": final_eval},
                                }
                            )
                allowed_figis_by_date[d.isoformat()] = sorted(day_selected_tickers)
                if day_selected_tickers:
                    ensured_intraday_tickers.update(day_selected_tickers)
                if bt_run_id:
                    try:
                        progress = round((len(day_stats) / max(1, len(trade_dates))) * 100.0, 2)
                        db.execute(
                            text(
                                """
                                UPDATE backtest.backtest_runs
                                SET progress_percent=:progress_percent
                                WHERE id=:id
                                """
                            ),
                            {"id": bt_run_id, "progress_percent": progress},
                        )
                        db.commit()
                    except Exception:
                        db.rollback()
            stage_logs.append(
                f"history: summary processed={processed_days}, skipped_fetch={skipped_fetch_days}, skipped_empty={skipped_empty_days}"
            )
            if missing_history_days:
                stage_logs.append(f"history: missing_days={','.join(missing_history_days)}")

            figis = sorted(set(selected_tickers))
            if not figis:
                dbg = f"processed={processed_days}, skipped_fetch={skipped_fetch_days}, skipped_empty={skipped_empty_days}, trade_dates={len(trade_dates)}"
                if last_history_error:
                    dbg = f"{dbg}, last_error={last_history_error}"
                if day_stats:
                    day_parts = []
                    for day, st in sorted(day_stats.items(), key=lambda x: x[0]):
                        day_parts.append(
                            f"{day}:rows={int(st.get('rows_total', 0))},fast={int(st.get('fast_passed', 0))},final={int(st.get('final_passed', 0))}"
                        )
                    dbg = f"{dbg}, day_stats=[{' | '.join(day_parts)}]"
                reject_reasons: Dict[str, int] = {}
                for dr in decisions_rows:
                    if str(dr.get("result") or "").upper() != "REJECT":
                        continue
                    rs = str(dr.get("reason") or "").strip() or "unknown"
                    reject_reasons[rs] = int(reject_reasons.get(rs, 0)) + 1
                if reject_reasons:
                    top = sorted(reject_reasons.items(), key=lambda x: x[1], reverse=True)[:3]
                    dbg = f"{dbg}, top_rejects={'; '.join([f'{k} x{v}' for k, v in top])}"
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Нет бумаг для бэктеста за выбранный период ({dbg})",
                )
            stage_logs.append(f"pipeline: selected {len(figis)} tickers")

            candles_by_figi: Dict[str, List[Dict[str, Any]]] = {}
            from_day = self._dt_date_utc(request.from_date)
            to_day = self._dt_date_utc(request.to_date)
            from_dt = datetime.combine(from_day, time.min, tzinfo=timezone.utc)
            to_dt_exclusive = datetime.combine(to_day + timedelta(days=1), time.min, tzinfo=timezone.utc)
            to_ts_shared = to_dt_exclusive - timedelta(microseconds=1)

            from app.modules.market_data_v1 import repository as shared_market_repository
            from app.modules.market_data_v1.intervals import strategy_interval_code_to_shared_canonical

            shared_canonical = strategy_interval_code_to_shared_canonical(interval_code_num)
            if shared_canonical and figis:
                try:
                    shared_rows = shared_market_repository.list_candles(
                        db,
                        tickers=figis,
                        board=board,
                        interval=shared_canonical,
                        from_ts=from_dt,
                        to_ts=to_ts_shared,
                    )
                except Exception as ex:
                    shared_rows = []
                    stage_logs.append(f"candles: shared_market_candles read failed ({ex}); will try legacy cache")
                by_ticker: Dict[str, List[Dict[str, Any]]] = {}
                for r in shared_rows or []:
                    tk = str((r or {}).get("ticker") or "").strip().upper()
                    if not tk:
                        continue
                    by_ticker.setdefault(tk, []).append(r)
                for tk, rows in by_ticker.items():
                    rows.sort(key=lambda x: x.get("bucket_start") or datetime.min.replace(tzinfo=timezone.utc))
                    one: List[Dict[str, Any]] = []
                    for c in rows:
                        close = float(c.get("close") or 0)
                        units = int(close)
                        nano = int(round((close - units) * 1_000_000_000))
                        bt = c.get("bucket_start")
                        time_iso = bt.isoformat() if hasattr(bt, "isoformat") else (str(bt) if bt else "")
                        one.append({
                            "time": time_iso,
                            "open": {"units": int(float(c.get("open") or 0)), "nano": 0},
                            "high": {"units": int(float(c.get("high") or 0)), "nano": 0},
                            "low": {"units": int(float(c.get("low") or 0)), "nano": 0},
                            "close": {"units": units, "nano": nano},
                            "volume": int(c.get("volume") or 0),
                        })
                    if one:
                        candles_by_figi[tk] = one
                stage_logs.append(
                    f"candles: shared_market_candles interval={shared_canonical} "
                    f"rows={len(shared_rows or [])} tickers_with_series={len(candles_by_figi)}"
                )
            elif not shared_canonical:
                stage_logs.append(
                    f"candles: no shared_market_candles mapping for interval_code={interval_code_num} "
                    f"(legacy candles_cache path)"
                )

            min_required_candles = 20 if interval_code_num in (1, 10, 60) else 1
            need_legacy = [
                tk for tk in figis
                if tk not in candles_by_figi or len(candles_by_figi.get(tk) or []) < min_required_candles
            ]
            candle_cache_stats: Dict[str, Any] = {
                "fetched_tickers": 0,
                "fetched_candles": 0,
            }
            if need_legacy:
                candle_cache_stats = await dms_service._ensure_candles_cached_for_tickers(
                    db=db,
                    board=board,
                    tickers=need_legacy,
                    interval_code=interval_code_num,
                    days_back=max(5, (to_day - from_day).days + 1),
                    from_date=from_day,
                    till_date=to_day,
                    refresh_recent_intraday=False,
                    min_candles_per_ticker=1,
                    user_id=user_id,
                )
                stage_logs.append(
                    f"candles: legacy cache ensure interval={interval_code} "
                    f"fetched_tickers={candle_cache_stats.get('fetched_tickers', 0)} "
                    f"fetched_candles={candle_cache_stats.get('fetched_candles', 0)} "
                    f"for {len(need_legacy)} ticker(s)"
                )

            for figi in need_legacy:
                c_rows = db.execute(
                    text(f"""
                        SELECT candle_time, open, high, low, close, volume
                        FROM {settings.DB_SCHEMA}.candles_cache
                        WHERE ticker = :ticker
                          AND interval = :interval
                          AND candle_time >= :from_date
                          AND candle_time < :to_date
                        ORDER BY candle_time ASC
                    """),
                    {
                        "ticker": figi,
                        "interval": interval_code,
                        "from_date": from_dt,
                        "to_date": to_dt_exclusive,
                    },
                ).mappings().all()
                if not c_rows and interval_code_num in (1, 10, 60):
                    c_rows = db.execute(
                        text(f"""
                            SELECT candle_time, open, high, low, close, volume
                            FROM {settings.DB_SCHEMA}.candles_cache
                            WHERE ticker = :ticker
                              AND interval IN (:interval_alias, :interval_i, :interval_plain, :interval_min)
                              AND candle_time >= :from_date
                              AND candle_time < :to_date
                            ORDER BY candle_time ASC
                        """),
                        {
                            "ticker": figi,
                            "interval_alias": interval_code,
                            "interval_i": f"I{interval_code_num}",
                            "interval_plain": f"{interval_code_num}m",
                            "interval_min": f"{interval_code_num}MIN",
                            "from_date": from_dt,
                            "to_date": to_dt_exclusive,
                        },
                    ).mappings().all()
                elif not c_rows and interval_code == "D1":
                    c_rows = db.execute(
                        text(f"""
                            SELECT candle_time, open, high, low, close, volume
                            FROM {settings.DB_SCHEMA}.candles_cache
                            WHERE ticker = :ticker
                              AND interval IN ('D1', 'I24', '1d', '1D', 'CANDLE_INTERVAL_DAY')
                              AND candle_time >= :from_date
                              AND candle_time < :to_date
                            ORDER BY candle_time ASC
                        """),
                        {
                            "ticker": figi,
                            "from_date": from_dt,
                            "to_date": to_dt_exclusive,
                        },
                    ).mappings().all()
                one: List[Dict[str, Any]] = []
                for c in c_rows:
                    close = float(c["close"] or 0)
                    units = int(close)
                    nano = int(round((close - units) * 1_000_000_000))
                    one.append({
                        "time": c["candle_time"].isoformat() if c["candle_time"] else "",
                        "open": {"units": int(float(c["open"] or 0)), "nano": 0},
                        "high": {"units": int(float(c["high"] or 0)), "nano": 0},
                        "low": {"units": int(float(c["low"] or 0)), "nano": 0},
                        "close": {"units": units, "nano": nano},
                        "volume": int(c["volume"] or 0),
                    })
                if one:
                    candles_by_figi[figi] = one

            missing_candle_tickers = [tk for tk in figis if tk not in candles_by_figi or len(candles_by_figi.get(tk) or []) < min_required_candles]
            if missing_candle_tickers:
                stage_logs.append(f"candles: missing in cache (history-only, no refetch) {len(missing_candle_tickers)}")

            if not candles_by_figi:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нет свечей для симуляции")
            stage_logs.append(f"candles: loaded for {len(candles_by_figi)} tickers")

            strategy_params["figis"] = list(candles_by_figi.keys())
            res = await run_backtest_simulation(
                candles_by_figi=candles_by_figi,
                strategy_name=strategy_name,
                strategy_params=strategy_params,
                risk_params=risk,
                initial_capital=request.initial_capital,
                robot_config_for_cost_defaults=config,
                allowed_figis_by_date=allowed_figis_by_date,
                execution_model=execution_model,
                slippage_pct=slippage_pct,
            )
            stage_logs.append("simulation: completed")
        except ValueError as e:
            try:
                db.execute(text(f"DELETE FROM {settings.DB_SCHEMA}.backtest_runs WHERE id=:run_id"), {"run_id": run_id})
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except HTTPException:
            try:
                db.execute(text(f"DELETE FROM {settings.DB_SCHEMA}.backtest_runs WHERE id=:run_id"), {"run_id": run_id})
                db.commit()
            except Exception:
                db.rollback()
            raise
        except Exception as e:
            logger.exception("robot history backtest failed")
            try:
                db.execute(text(f"DELETE FROM {settings.DB_SCHEMA}.backtest_runs WHERE id=:run_id"), {"run_id": run_id})
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Ошибка загрузки данных или расчёта: {e}",
            )

        result = {
            "run_id": int(run_id),
            "initial_capital": res.initial_capital,
            "final_equity": res.final_equity,
            "total_return_percent": res.total_return_percent,
            "max_drawdown_percent": res.max_drawdown_percent,
            "trades": res.trades,
            "equity_curve": res.equity_curve,
            "stages": stage_logs,
            "history_stats": {
                "processed": processed_days,
                "skipped_fetch": skipped_fetch_days,
                "skipped_empty": skipped_empty_days,
                "total_trade_dates": len(trade_dates),
            },
        }
        # Daily summary for UI: candidates/signals/trades breakdown by day.
        try:
            daily_map: Dict[str, Dict[str, int]] = {}
            for d in trade_dates:
                key = d.isoformat()
                daily_map[key] = {
                    "candidates_accept": 0,
                    "candidates_reject": 0,
                    "signals_total": 0,
                    "signals_executed": 0,
                    "trades_total": 0,
                }
            for dr in decisions_rows:
                day = str(dr.get("trade_date") or "")
                if not day:
                    continue
                if day not in daily_map:
                    daily_map[day] = {
                        "candidates_accept": 0,
                        "candidates_reject": 0,
                        "signals_total": 0,
                        "signals_executed": 0,
                        "trades_total": 0,
                    }
                if str(dr.get("result") or "").upper() == "ACCEPT":
                    daily_map[day]["candidates_accept"] += 1
                else:
                    daily_map[day]["candidates_reject"] += 1
            for s in res.signals:
                bt = str(s.get("bar_time") or "")
                day = bt[:10] if len(bt) >= 10 else ""
                if not day:
                    continue
                if day not in daily_map:
                    daily_map[day] = {
                        "candidates_accept": 0,
                        "candidates_reject": 0,
                        "signals_total": 0,
                        "signals_executed": 0,
                        "trades_total": 0,
                    }
                daily_map[day]["signals_total"] += 1
                if int(bool(s.get("was_executed"))):
                    daily_map[day]["signals_executed"] += 1
            for t in res.trades:
                bt = str(t.get("bar_time") or "")
                day = bt[:10] if len(bt) >= 10 else ""
                if not day:
                    continue
                if day not in daily_map:
                    daily_map[day] = {
                        "candidates_accept": 0,
                        "candidates_reject": 0,
                        "signals_total": 0,
                        "signals_executed": 0,
                        "trades_total": 0,
                    }
                daily_map[day]["trades_total"] += 1
            result["daily_summary"] = [
                {"date": d, **vals}
                for d, vals in sorted(daily_map.items(), key=lambda x: x[0])
            ]
        except Exception:
            # Do not fail backtest response on analytics post-processing.
            result["daily_summary"] = []
        try:
            for p in res.equity_curve:
                tm = p.get("time")
                ts = datetime.now(timezone.utc)
                try:
                    if tm:
                        ts = datetime.fromisoformat(str(tm).replace("Z", "+00:00"))
                except Exception:
                    pass
                db.execute(
                    text(f"""
                        INSERT INTO {settings.DB_SCHEMA}.backtest_portfolio_snapshots
                        (run_id, snapshot_time, cash_balance, equity, positions_payload)
                        VALUES (:run_id, :snapshot_time, :cash_balance, :equity, '[]'::jsonb)
                    """),
                    {
                        "run_id": run_id,
                        "snapshot_time": ts,
                        "cash_balance": p.get("equity", 0),
                        "equity": p.get("equity", 0),
                    },
                )
            for t in res.trades:
                t_time = None
                try:
                    if t.get("bar_time"):
                        t_time = datetime.fromisoformat(str(t.get("bar_time")).replace("Z", "+00:00"))
                except Exception:
                    t_time = None
                db.execute(
                    text(f"""
                        INSERT INTO {settings.DB_SCHEMA}.backtest_orders
                        (run_id, signal_time, figi, side, status, quantity, requested_price, executed_price, slippage_pct, commission, tax, pnl_net, payload)
                        VALUES (:run_id, :signal_time, :figi, :side, :status, :quantity, :requested_price, :executed_price, :slippage_pct, :commission, :tax, :pnl_net, CAST(:payload AS jsonb))
                    """),
                    {
                        "run_id": run_id,
                        "signal_time": t_time,
                        "figi": t.get("figi"),
                        "side": t.get("side"),
                        "status": "FILLED",
                        "quantity": t.get("quantity", 0),
                        "requested_price": t.get("price"),
                        "executed_price": t.get("price"),
                        "slippage_pct": slippage_pct,
                        "commission": t.get("commission"),
                        "tax": None,
                        "pnl_net": t.get("pnl_net"),
                        "payload": json.dumps(t, ensure_ascii=False),
                    },
                )
            for s in res.signals:
                s_time = None
                try:
                    if s.get("bar_time"):
                        s_time = datetime.fromisoformat(str(s.get("bar_time")).replace("Z", "+00:00"))
                except Exception:
                    s_time = None
                db.execute(
                    text(f"""
                        INSERT INTO {settings.DB_SCHEMA}.backtest_signals
                        (run_id, signal_time, figi, signal_type, price, was_executed, payload)
                        VALUES (:run_id, :signal_time, :figi, :signal_type, :price, :was_executed, CAST(:payload AS jsonb))
                    """),
                    {
                        "run_id": run_id,
                        "signal_time": s_time,
                        "figi": s.get("figi"),
                        "signal_type": s.get("signal_type"),
                        "price": s.get("price"),
                        "was_executed": int(bool(s.get("was_executed"))),
                        "payload": json.dumps(s, ensure_ascii=False),
                    },
                )
            for dr in decisions_rows:
                db.execute(
                    text(
                        f"""
                        INSERT INTO {settings.DB_SCHEMA}.backtest_decisions
                        (run_id, trade_date, ticker, source, result, reason, payload)
                        VALUES (:run_id, :trade_date, :ticker, 'PIPELINE', :result, :reason, CAST(:payload AS jsonb))
                        """
                    ),
                    {
                        "run_id": run_id,
                        "trade_date": dr.get("trade_date"),
                        "ticker": dr.get("ticker"),
                        "result": dr.get("result"),
                        "reason": dr.get("reason"),
                        "payload": json.dumps(dr.get("payload") or {}, ensure_ascii=False),
                    },
                )
                if bt_run_id:
                    try:
                        eval_payload = dr.get("payload") if isinstance(dr.get("payload"), dict) else {}
                        eval_obj = eval_payload.get("eval") if isinstance(eval_payload, dict) else {}
                        db.execute(
                            text(
                                """
                                INSERT INTO backtest.backtest_daily_universe
                                (backtest_run_id, trade_date, ticker, source, filter_result, reject_reason, snapshot_id,
                                 price_at_filter, volume_at_filter, atr_value, gap_percent, applied_filters)
                                VALUES
                                (:backtest_run_id, :trade_date, :ticker, :source, :filter_result, :reject_reason, NULL,
                                 :price_at_filter, :volume_at_filter, :atr_value, :gap_percent, CAST(:applied_filters AS jsonb))
                                ON CONFLICT (backtest_run_id, trade_date, ticker) DO UPDATE SET
                                    filter_result = EXCLUDED.filter_result,
                                    reject_reason = EXCLUDED.reject_reason,
                                    price_at_filter = EXCLUDED.price_at_filter,
                                    volume_at_filter = EXCLUDED.volume_at_filter,
                                    atr_value = EXCLUDED.atr_value,
                                    gap_percent = EXCLUDED.gap_percent,
                                    applied_filters = EXCLUDED.applied_filters
                                """
                            ),
                            {
                                "backtest_run_id": bt_run_id,
                                "trade_date": dr.get("trade_date"),
                                "ticker": dr.get("ticker"),
                                "source": "PIPELINE",
                                "filter_result": "ACCEPT" if str(dr.get("result") or "").upper() == "ACCEPT" else "REJECT",
                                "reject_reason": dr.get("reason"),
                                "price_at_filter": eval_obj.get("price_at_filter"),
                                "volume_at_filter": eval_obj.get("volume_at_filter"),
                                "atr_value": eval_obj.get("atr_percent"),
                                "gap_percent": eval_obj.get("gap_percent"),
                                "applied_filters": json.dumps(eval_payload, ensure_ascii=False),
                            },
                        )
                    except Exception:
                        db.rollback()
            m = BacktestMetricsCalculator.calculate(res=res)
            winning = list(m["winning"])
            closed = list(m["closed"])
            avg_pnl = m["avg_pnl"]
            win_rate = m["win_rate"]
            gross_profit_val = float(m["gross_profit_val"])
            gross_loss_val = float(m["gross_loss_val"])
            net_profit_val = float(m["net_profit_val"])
            total_commission_val = float(m["total_commission_val"])
            profit_factor_val = m["profit_factor_val"]
            avg_win_val = m["avg_win_val"]
            avg_loss_val = m["avg_loss_val"]
            equity_by_day = dict(m["equity_by_day"])
            trading_days_cnt = int(m["trading_days_cnt"] or 0)
            annualized_return_val = m["annualized_return_val"]
            volatility_annual_val = m["volatility_annual_val"]
            sharpe_val = m["sharpe_val"]
            sortino_val = m["sortino_val"]
            calmar_val = m["calmar_val"]
            max_dd_duration = int(m["max_dd_duration"] or 0)
            if bt_run_id:
                persist_payload = BacktestPersistPayload(
                    equity_by_day=equity_by_day,
                    trading_days_cnt=trading_days_cnt,
                    win_rate=win_rate,
                    annualized_return_val=annualized_return_val,
                    max_dd_duration=max_dd_duration,
                    sharpe_val=sharpe_val,
                    sortino_val=sortino_val,
                    calmar_val=calmar_val,
                    volatility_annual_val=volatility_annual_val,
                    gross_profit_val=gross_profit_val,
                    gross_loss_val=gross_loss_val,
                    total_commission_val=total_commission_val,
                    net_profit_val=net_profit_val,
                    profit_factor_val=profit_factor_val,
                    avg_pnl=avg_pnl,
                    avg_win_val=avg_win_val,
                    avg_loss_val=avg_loss_val,
                    winning_count=len(winning),
                    closed_count=len(closed),
                    start_date=self._dt_date_utc(request.from_date),
                    end_date=self._dt_date_utc(request.to_date),
                )
                BacktestPersistence(db).persist_run_details(
                    bt_run_id=bt_run_id,
                    res=res,
                    slippage_pct=slippage_pct,
                    payload=persist_payload,
                )
            db.execute(
                text(f"""
                    INSERT INTO {settings.DB_SCHEMA}.backtest_metrics
                    (run_id, total_return_percent, max_drawdown_percent, sharpe_ratio, trades_total, win_rate_percent, avg_pnl_per_trade, final_equity, payload)
                    VALUES (:run_id, :total_return_percent, :max_drawdown_percent, NULL, :trades_total, :win_rate_percent, :avg_pnl_per_trade, :final_equity, CAST(:payload AS jsonb))
                    ON CONFLICT (run_id) DO UPDATE SET
                        total_return_percent = EXCLUDED.total_return_percent,
                        max_drawdown_percent = EXCLUDED.max_drawdown_percent,
                        trades_total = EXCLUDED.trades_total,
                        win_rate_percent = EXCLUDED.win_rate_percent,
                        avg_pnl_per_trade = EXCLUDED.avg_pnl_per_trade,
                        final_equity = EXCLUDED.final_equity,
                        payload = EXCLUDED.payload
                """),
                {
                    "run_id": run_id,
                    "total_return_percent": res.total_return_percent,
                    "max_drawdown_percent": res.max_drawdown_percent,
                    "trades_total": len(res.trades),
                    "win_rate_percent": win_rate,
                    "avg_pnl_per_trade": avg_pnl,
                    "final_equity": res.final_equity,
                    "payload": json.dumps(result, ensure_ascii=False),
                },
            )
            db.execute(
                text(f"""
                    UPDATE {settings.DB_SCHEMA}.backtest_runs
                    SET status='SUCCESS',
                        finished_at=:finished_at,
                        metrics_summary=CAST(:summary AS jsonb)
                    WHERE id=:run_id
                """),
                {
                    "run_id": run_id,
                    "finished_at": datetime.now(timezone.utc),
                    "summary": json.dumps({
                        "total_return_percent": res.total_return_percent,
                        "max_drawdown_percent": res.max_drawdown_percent,
                        "trades_total": len(res.trades),
                        "final_equity": res.final_equity,
                    }, ensure_ascii=False),
                },
            )
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
            db.execute(
                text(f"""
                    UPDATE {settings.DB_SCHEMA}.backtest_runs
                    SET status='FAILED',
                        finished_at=:finished_at,
                        error_message=:error_message
                    WHERE id=:run_id
                """),
                {
                    "run_id": run_id,
                    "finished_at": datetime.now(timezone.utc),
                    "error_message": "persist-failed",
                },
            )
            db.commit()
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
            FROM {settings.DB_SCHEMA}.backtest_runs br
            WHERE br.robot_id = :robot_id
              AND br.status = 'SUCCESS'
        """
        total = int(db.execute(text(total_sql), {"robot_id": robot_id}).scalar() or 0)

        rows_sql = f"""
            SELECT
                br.id,
                br.robot_id,
                br.requested_from,
                br.requested_to,
                br.initial_capital,
                COALESCE(bm.final_equity, 0) AS final_equity,
                COALESCE(bm.total_return_percent, 0) AS total_return_percent,
                bm.max_drawdown_percent,
                br.started_at AS created_at,
                COALESCE(bm.payload, '{{}}'::jsonb) AS result_payload
            FROM {settings.DB_SCHEMA}.backtest_runs br
            LEFT JOIN {settings.DB_SCHEMA}.backtest_metrics bm ON bm.run_id = br.id
            WHERE br.robot_id = :robot_id
              AND br.status = 'SUCCESS'
            ORDER BY br.started_at DESC
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

    async def get_backtest_run_details(
            self,
            db: Session,
            run_id: int,
            user_id: int,
    ) -> Dict[str, Any]:
        header = db.execute(
            text(f"""
                SELECT
                    br.id,
                    br.robot_id,
                    br.status,
                    br.requested_from,
                    br.requested_to,
                    br.started_at,
                    br.finished_at,
                    br.initial_capital,
                    bm.total_return_percent,
                    bm.max_drawdown_percent,
                    bm.final_equity,
                    bm.trades_total,
                    COALESCE(bm.payload, '{{}}'::jsonb) AS result_payload
                FROM {settings.DB_SCHEMA}.backtest_runs br
                LEFT JOIN {settings.DB_SCHEMA}.backtest_metrics bm ON bm.run_id = br.id
                WHERE br.id = :run_id
                LIMIT 1
            """),
            {"run_id": run_id},
        ).first()
        if not header:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Прогон не найден")
        robot_id = int(header[1])
        await self.get_robot_by_id(db, robot_id, user_id)

        signals_rows = db.execute(
            text(f"""
                SELECT id, signal_time, figi, signal_type, price, was_executed, payload
                FROM {settings.DB_SCHEMA}.backtest_signals
                WHERE run_id = :run_id
                ORDER BY id ASC
            """),
            {"run_id": run_id},
        ).fetchall()
        orders_rows = db.execute(
            text(f"""
                SELECT id, signal_time, figi, side, status, quantity, requested_price, executed_price, slippage_pct, commission, tax, pnl_net, payload
                FROM {settings.DB_SCHEMA}.backtest_orders
                WHERE run_id = :run_id
                ORDER BY id ASC
            """),
            {"run_id": run_id},
        ).fetchall()
        portfolio_rows = db.execute(
            text(f"""
                SELECT id, snapshot_time, cash_balance, equity, positions_payload
                FROM {settings.DB_SCHEMA}.backtest_portfolio_snapshots
                WHERE run_id = :run_id
                ORDER BY snapshot_time ASC
            """),
            {"run_id": run_id},
        ).fetchall()
        decisions_rows = db.execute(
            text(f"""
                SELECT trade_date, result
                FROM {settings.DB_SCHEMA}.backtest_decisions
                WHERE run_id = :run_id
            """),
            {"run_id": run_id},
        ).fetchall()

        payload_obj = header[12] or {}
        payload_daily_summary = []
        if isinstance(payload_obj, dict):
            payload_daily_summary = list(payload_obj.get("daily_summary") or [])
        daily_summary = payload_daily_summary
        if not daily_summary:
            day_map: Dict[str, Dict[str, int]] = {}
            for dr in decisions_rows:
                d = str(dr[0])
                if d not in day_map:
                    day_map[d] = {"candidates_accept": 0, "candidates_reject": 0, "signals_total": 0, "signals_executed": 0, "trades_total": 0}
                if str(dr[1] or "").upper() == "ACCEPT":
                    day_map[d]["candidates_accept"] += 1
                else:
                    day_map[d]["candidates_reject"] += 1
            for r in signals_rows:
                d = str(r[1])[:10] if r[1] else ""
                if not d:
                    continue
                if d not in day_map:
                    day_map[d] = {"candidates_accept": 0, "candidates_reject": 0, "signals_total": 0, "signals_executed": 0, "trades_total": 0}
                day_map[d]["signals_total"] += 1
                if bool(r[5]):
                    day_map[d]["signals_executed"] += 1
            for r in orders_rows:
                d = str(r[1])[:10] if r[1] else ""
                if not d:
                    continue
                if d not in day_map:
                    day_map[d] = {"candidates_accept": 0, "candidates_reject": 0, "signals_total": 0, "signals_executed": 0, "trades_total": 0}
                day_map[d]["trades_total"] += 1
            daily_summary = [{"date": d, **vals} for d, vals in sorted(day_map.items(), key=lambda x: x[0])]

        return {
            "run_id": int(header[0]),
            "robot_id": robot_id,
            "status": str(header[2] or "UNKNOWN"),
            "requested_from": header[3],
            "requested_to": header[4],
            "started_at": header[5],
            "finished_at": header[6],
            "initial_capital": float(header[7] or 0),
            "total_return_percent": float(header[8]) if header[8] is not None else None,
            "max_drawdown_percent": float(header[9]) if header[9] is not None else None,
            "final_equity": float(header[10]) if header[10] is not None else None,
            "trades_total": int(header[11] or 0),
            "result_payload": payload_obj,
            "signals": [
                {
                    "id": int(r[0]),
                    "signal_time": r[1],
                    "figi": r[2],
                    "signal_type": r[3],
                    "price": float(r[4]) if r[4] is not None else None,
                    "was_executed": bool(r[5]),
                    "payload": r[6] or {},
                }
                for r in signals_rows
            ],
            "orders": [
                {
                    "id": int(r[0]),
                    "signal_time": r[1],
                    "figi": r[2],
                    "side": r[3],
                    "status": r[4],
                    "quantity": float(r[5] or 0),
                    "requested_price": float(r[6]) if r[6] is not None else None,
                    "executed_price": float(r[7]) if r[7] is not None else None,
                    "slippage_pct": float(r[8] or 0),
                    "commission": float(r[9]) if r[9] is not None else None,
                    "tax": float(r[10]) if r[10] is not None else None,
                    "pnl_net": float(r[11]) if r[11] is not None else None,
                    "payload": r[12] or {},
                }
                for r in orders_rows
            ],
            "portfolio_snapshots": [
                {
                    "id": int(r[0]),
                    "snapshot_time": r[1],
                    "cash_balance": float(r[2] or 0),
                    "equity": float(r[3] or 0),
                    "positions_payload": r[4] or [],
                }
                for r in portfolio_rows
            ],
            "daily_summary": daily_summary,
        }

    async def compare_backtest_runs(
            self,
            db: Session,
            base_run_id: int,
            compare_run_id: int,
            user_id: int,
            name: Optional[str] = None,
    ) -> Dict[str, Any]:
        def _run_header(run_id: int):
            row = db.execute(
                text(
                    f"""
                    SELECT br.id, br.robot_id, br.requested_from, br.requested_to, br.config_snapshot,
                           bm.total_return_percent, bm.max_drawdown_percent, bm.final_equity, bm.trades_total, bm.win_rate_percent
                    FROM {settings.DB_SCHEMA}.backtest_runs br
                    LEFT JOIN {settings.DB_SCHEMA}.backtest_metrics bm ON bm.run_id = br.id
                    WHERE br.id=:run_id
                    LIMIT 1
                    """
                ),
                {"run_id": run_id},
            ).first()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Прогон {run_id} не найден")
            return row

        base = _run_header(base_run_id)
        comp = _run_header(compare_run_id)
        await self.get_robot_by_id(db, int(base[1]), user_id)
        await self.get_robot_by_id(db, int(comp[1]), user_id)

        def _as_float(v: Any) -> Optional[float]:
            try:
                return float(v) if v is not None else None
            except Exception:
                return None

        base_metrics = {
            "total_return_percent": _as_float(base[5]),
            "max_drawdown_percent": _as_float(base[6]),
            "final_equity": _as_float(base[7]),
            "trades_total": int(base[8] or 0),
            "win_rate_percent": _as_float(base[9]),
        }
        comp_metrics = {
            "total_return_percent": _as_float(comp[5]),
            "max_drawdown_percent": _as_float(comp[6]),
            "final_equity": _as_float(comp[7]),
            "trades_total": int(comp[8] or 0),
            "win_rate_percent": _as_float(comp[9]),
        }
        metrics_diff = {}
        for k in base_metrics.keys():
            bv = base_metrics[k]
            cv = comp_metrics[k]
            if isinstance(bv, (int, float)) and isinstance(cv, (int, float)):
                metrics_diff[k] = cv - bv
            else:
                metrics_diff[k] = None

        base_cfg = base[4] if isinstance(base[4], dict) else {}
        comp_cfg = comp[4] if isinstance(comp[4], dict) else {}
        keys = sorted(set(base_cfg.keys()) | set(comp_cfg.keys()))
        cfg_diff = {
            k: {"base": base_cfg.get(k), "compare": comp_cfg.get(k)}
            for k in keys
            if base_cfg.get(k) != comp_cfg.get(k)
        }

        cmp_id = int(
            db.execute(
                text(
                    """
                    INSERT INTO backtest.backtest_comparisons
                    (name, base_run_id, compare_run_id, config_diff)
                    VALUES (:name, :base_run_id, :compare_run_id, CAST(:config_diff AS jsonb))
                    RETURNING id
                    """
                ),
                {
                    "name": name or f"run-{base_run_id}-vs-{compare_run_id}",
                    "base_run_id": base_run_id,
                    "compare_run_id": compare_run_id,
                    "config_diff": json.dumps(cfg_diff, ensure_ascii=False),
                },
            ).scalar()
            or 0
        )
        db.commit()

        return {
            "comparison_id": cmp_id,
            "name": name or f"run-{base_run_id}-vs-{compare_run_id}",
            "base_run_id": base_run_id,
            "compare_run_id": compare_run_id,
            "metrics_base": base_metrics,
            "metrics_compare": comp_metrics,
            "metrics_diff": metrics_diff,
            "config_diff": cfg_diff,
        }

    async def list_backtest_comparisons(
            self,
            db: Session,
            user_id: int,
            limit: int = 30,
            offset: int = 0,
    ) -> Dict[str, Any]:
        total = int(
            db.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM backtest.backtest_comparisons c
                    JOIN {settings.DB_SCHEMA}.backtest_runs b ON b.id = c.base_run_id
                    JOIN {settings.DB_SCHEMA}.backtest_runs r ON r.id = c.compare_run_id
                    JOIN {settings.DB_SCHEMA}.robots rb ON rb.id = b.robot_id
                    JOIN {settings.DB_SCHEMA}.robots rr ON rr.id = r.robot_id
                    WHERE rb.user_id = :user_id AND rr.user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            ).scalar()
            or 0
        )
        rows = db.execute(
            text(
                f"""
                SELECT c.id, c.name, c.base_run_id, c.compare_run_id, c.config_diff, c.created_at
                FROM backtest.backtest_comparisons c
                JOIN {settings.DB_SCHEMA}.backtest_runs b ON b.id = c.base_run_id
                JOIN {settings.DB_SCHEMA}.backtest_runs r ON r.id = c.compare_run_id
                JOIN {settings.DB_SCHEMA}.robots rb ON rb.id = b.robot_id
                JOIN {settings.DB_SCHEMA}.robots rr ON rr.id = r.robot_id
                WHERE rb.user_id = :user_id AND rr.user_id = :user_id
                ORDER BY c.created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"user_id": user_id, "limit": limit, "offset": offset},
        ).fetchall()
        items = [
            {
                "id": int(r[0]),
                "name": str(r[1] or ""),
                "base_run_id": int(r[2]),
                "compare_run_id": int(r[3]),
                "config_diff": r[4] or {},
                "created_at": r[5],
            }
            for r in rows
        ]
        return {"total": total, "items": items}

    async def get_backtest_comparison(
            self,
            db: Session,
            comparison_id: int,
            user_id: int,
    ) -> Dict[str, Any]:
        row = db.execute(
            text(
                f"""
                SELECT c.id, c.name, c.base_run_id, c.compare_run_id
                FROM backtest.backtest_comparisons c
                JOIN {settings.DB_SCHEMA}.backtest_runs b ON b.id = c.base_run_id
                JOIN {settings.DB_SCHEMA}.backtest_runs r ON r.id = c.compare_run_id
                JOIN {settings.DB_SCHEMA}.robots rb ON rb.id = b.robot_id
                JOIN {settings.DB_SCHEMA}.robots rr ON rr.id = r.robot_id
                WHERE c.id = :comparison_id
                  AND rb.user_id = :user_id
                  AND rr.user_id = :user_id
                LIMIT 1
                """
            ),
            {"comparison_id": comparison_id, "user_id": user_id},
        ).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сравнение не найдено")
        return await self.compare_backtest_runs(
            db=db,
            base_run_id=int(row[2]),
            compare_run_id=int(row[3]),
            user_id=user_id,
            name=str(row[1] or f"cmp-{comparison_id}"),
        )

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
        known_fields = set(schemas.GrainSeedConfig.model_fields.keys())
        extra_fields = {k: v for k, v in (config or {}).items() if k not in known_fields}
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
        config.update(extra_fields)


# Создаем экземпляр сервиса
robot_service = RobotService()
