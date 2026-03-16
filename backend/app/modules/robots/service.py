# app/modules/robots/service.py
from typing import Optional, List, Dict, Any, Tuple
import logging
from datetime import datetime, timezone
import asyncio
import json

from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

from app.modules.tinvest.token_service import token_service
from app.modules.tinvest.service import tinvest_service
from . import queries, schemas
from .portfolio_updater.robot import PortfolioUpdaterRobot  # ← ИСПРАВЛЕНО
from .portfolio_updater.scheduler import PortfolioUpdaterScheduler  # ← ИСПРАВЛЕНО

logger = logging.getLogger(__name__)


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

    def _row_to_robot_dict(self, row) -> dict:
        """Преобразует строку результата в словарь робота"""
        if not row or len(row) < 22:
            return {}

        return {
            "id": self._safe_int(row[0]),
            "user_id": self._safe_int(row[1]),
            "token_id": self._safe_int(row[2]) if row[2] is not None else None,
            "name": self._safe_str(row[3]),
            "description": self._safe_str(row[4], None),
            "robot_type": self._safe_str(row[5]),
            "strategy_params": row[6] if row[6] else {},
            "max_daily_loss": self._safe_float(row[7], None),
            "max_position_size": self._safe_float(row[8], None),
            "allowed_instruments": row[9] if row[9] else [],
            "status": self._safe_str(row[10]),
            "is_active": self._safe_bool(row[11]),
            "total_trades": self._safe_int(row[12]),
            "successful_trades": self._safe_int(row[13]),
            "total_profit": self._safe_float(row[14]),
            "total_profit_percent": self._safe_float(row[15]),
            "created_at": self._safe_datetime(row[16]),
            "updated_at": self._safe_datetime(row[17]),
            "started_at": self._safe_datetime(row[18]),
            "stopped_at": self._safe_datetime(row[19]),
            "last_error": self._safe_str(row[20], None),
            "last_error_at": self._safe_datetime(row[21]),
        }

    def _row_to_trade_dict(self, row) -> dict:
        """Преобразует строку результата в словарь сделки"""
        if not row or len(row) < 17:
            return {}

        return {
            "id": self._safe_int(row[0]),
            "robot_id": self._safe_int(row[1]),
            "figi": self._safe_str(row[2]),
            "ticker": self._safe_str(row[3], None),
            "instrument_type": self._safe_str(row[4]),
            "side": self._safe_str(row[5]),
            "quantity": self._safe_float(row[6]),
            "price": self._safe_float(row[7]),
            "total_amount": self._safe_float(row[8]),
            "commission": self._safe_float(row[9], None),
            "commission_currency": self._safe_str(row[10], None),
            "order_id": self._safe_str(row[11], None),
            "profit": self._safe_float(row[12], None),
            "profit_percent": self._safe_float(row[13], None),
            "status": self._safe_str(row[14]),
            "created_at": self._safe_datetime(row[15]),
            "closed_at": self._safe_datetime(row[16]),
        }

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

    async def get_user_robots(
            self,
            db: Session,
            user_id: int,
            include_inactive: bool = False,
            robot_type: Optional[str] = None
    ) -> List[dict]:
        """Получение всех роботов пользователя"""
        self.db = db

        query, params_template = queries.build_get_user_robots_query(
            include_inactive=include_inactive,
            robot_type=robot_type
        )

        params = {"user_id": user_id}
        if robot_type:
            params["robot_type"] = robot_type

        results = self._execute(query, params).fetchall()

        robots = []
        for row in results:
            robot_dict = self._row_to_robot_dict(row)
            robots.append(robot_dict)

        return robots

    async def get_robot_by_id(
            self,
            db: Session,
            robot_id: int,
            user_id: int
    ) -> Optional[dict]:
        """Получение робота по ID (с проверкой владельца)"""
        self.db = db

        query = queries.build_get_robot_by_id_query()
        result = self._execute(
            query,
            {"robot_id": robot_id, "user_id": user_id},
            fetch_one=True
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Робот не найден"
            )

        return self._row_to_robot_dict(result)

    async def create_robot(
            self,
            db: Session,
            user_id: int,
            robot_data: schemas.RobotCreate
    ) -> dict:
        """Создание нового робота"""
        self.db = db

        # Проверяем токен, если указан
        if robot_data.token_id:
            token = await token_service.get_token_by_id(
                db,
                robot_data.token_id,
                user_id
            )
            if not token or not token.get("is_active"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Выбранный токен не активен"
                )

        now = datetime.now(timezone.utc)

        # Создаем робота
        insert_query = queries.build_create_robot_query()
        result = self._execute(
            insert_query,
            {
                "user_id": user_id,
                "token_id": robot_data.token_id,
                "name": robot_data.name,
                "description": robot_data.description,
                "robot_type": robot_data.robot_type,
                "strategy_params": json.dumps(robot_data.strategy_params or {}),
                "max_daily_loss": robot_data.max_daily_loss,
                "max_position_size": robot_data.max_position_size,
                "allowed_instruments": json.dumps(robot_data.allowed_instruments or []),
                "status": "stopped",
                "is_active": 0,
                "created_at": now
            },
            fetch_one=True
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать робота"
            )

        db.commit()

        robot_dict = self._row_to_robot_dict(result)

        # Добавляем лог
        await self._add_log(db, robot_dict["id"], "INFO", f"Робот '{robot_dict['name']}' создан")

        logger.info(f"✅ Created robot {robot_dict['id']} for user {user_id}")

        return robot_dict

    async def update_robot(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            robot_data: schemas.RobotUpdate
    ) -> dict:
        """Обновление робота"""
        self.db = db

        # Получаем текущего робота
        robot = await self.get_robot_by_id(db, robot_id, user_id)

        # Если робот активен, запрещаем некоторые изменения
        if robot.get("status") == "active":
            forbidden_fields = ["token_id", "strategy_params", "max_daily_loss", "max_position_size"]
            changes = robot_data.model_dump(exclude_unset=True)
            if any(field in changes for field in forbidden_fields):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Нельзя изменять параметры стратегии у активного робота. Сначала остановите робота."
                )

        # Проверяем токен, если меняется
        if robot_data.token_id is not None and robot_data.token_id != robot.get("token_id"):
            token = await token_service.get_token_by_id(db, robot_data.token_id, user_id)
            if not token or not token.get("is_active"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Выбранный токен не активен"
                )

        # Определяем, какие поля обновляем
        update_data = robot_data.model_dump(exclude_unset=True, exclude_none=True)
        fields_to_update = list(update_data.keys())

        if not fields_to_update:
            return robot

        # Строим запрос обновления
        update_query, _ = queries.build_update_robot_query(fields_to_update)

        params = {
            "robot_id": robot_id,
            "user_id": user_id,
            "now": datetime.now(timezone.utc)
        }

        # Добавляем значения полей
        for field in fields_to_update:
            value = update_data[field]
            if field in ["strategy_params", "allowed_instruments"] and value is not None:
                params[field] = json.dumps(value)
            else:
                params[field] = value

        result = self._execute(update_query, params, fetch_one=True)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить робота"
            )

        db.commit()

        robot_dict = self._row_to_robot_dict(result)

        await self._add_log(db, robot_id, "INFO", f"Робот '{robot_dict['name']}' обновлен")
        logger.info(f"✅ Updated robot {robot_id} for user {user_id}")

        return robot_dict

    async def delete_robot(self, db: Session, robot_id: int, user_id: int) -> bool:
        """Удаление робота"""
        self.db = db

        # Проверяем статус
        robot = await self.get_robot_by_id(db, robot_id, user_id)

        if robot.get("status") == "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя удалить активного робота. Сначала остановите робота."
            )

        query = queries.build_delete_robot_query()
        result = self._execute(
            query,
            {"robot_id": robot_id, "user_id": user_id},
            fetch_one=True
        )

        if result:
            db.commit()
            logger.info(f"✅ Deleted robot {robot_id} for user {user_id}")
            return True

        return False

    # === УПРАВЛЕНИЕ СОСТОЯНИЕМ ===

    async def start_robot(self, db: Session, robot_id: int, user_id: int) -> dict:
        """Запуск робота"""
        self.db = db

        robot = await self.get_robot_by_id(db, robot_id, user_id)

        # Проверяем наличие токена
        if not robot.get("token_id"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для запуска робота необходимо выбрать токен доступа"
            )

        # Проверяем активность токена
        token = await token_service.get_token_by_id(db, robot["token_id"], user_id)
        if not token or not token.get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Выбранный токен не активен"
            )

        now = datetime.now(timezone.utc)

        # Обновляем статус
        update_query, _ = queries.build_update_robot_query(["status", "is_active", "started_at"])

        result = self._execute(
            update_query,
            {
                "robot_id": robot_id,
                "user_id": user_id,
                "status": "active",
                "is_active": 1,
                "started_at": now,
                "now": now
            },
            fetch_one=True
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось запустить робота"
            )

        db.commit()

        robot_dict = self._row_to_robot_dict(result)

        await self._add_log(db, robot_id, "INFO", f"Робот '{robot_dict['name']}' запущен")
        logger.info(f"✅ Started robot {robot_id} for user {user_id}")

        # Запускаем основной цикл робота в фоне
        asyncio.create_task(self._run_robot_loop(db, robot_id, user_id))

        return robot_dict

    async def stop_robot(self, db: Session, robot_id: int, user_id: int) -> dict:
        """Остановка робота"""
        self.db = db

        now = datetime.now(timezone.utc)

        # Обновляем статус
        update_query, _ = queries.build_update_robot_query(["status", "is_active", "stopped_at"])

        result = self._execute(
            update_query,
            {
                "robot_id": robot_id,
                "user_id": user_id,
                "status": "stopped",
                "is_active": 0,
                "stopped_at": now,
                "now": now
            },
            fetch_one=True
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось остановить робота"
            )

        db.commit()

        robot_dict = self._row_to_robot_dict(result)

        await self._add_log(db, robot_id, "INFO", f"Робот '{robot_dict['name']}' остановлен")
        logger.info(f"✅ Stopped robot {robot_id} for user {user_id}")

        return robot_dict

    # === ОСНОВНОЙ ЦИКЛ РОБОТА ===

    async def _run_robot_loop(self, db: Session, robot_id: int, user_id: int):
        """Основной цикл работы робота (запускается в фоне)"""
        logger.info(f"🔄 Starting robot loop for robot {robot_id}")

        while True:
            try:
                # Получаем актуальное состояние робота
                robot = await self.get_robot_by_id(db, robot_id, user_id)

                # Если робот остановлен, выходим из цикла
                if robot.get("status") != "active":
                    logger.info(f"⏹️ Robot {robot_id} is not active, stopping loop")
                    break

                # Получаем токен
                token = await token_service.get_token_by_id(db, robot.get("token_id"), user_id)
                if not token or not token.get("is_active"):
                    await self._handle_error(db, robot, "Токен не активен")
                    break

                # Здесь будет логика конкретного робота в зависимости от типа
                if robot.get("robot_type") == "grid":
                    await self._run_grid_strategy(db, robot, token.get("token"))
                elif robot.get("robot_type") == "trend":
                    await self._run_trend_strategy(db, robot, token.get("token"))
                else:
                    await self._add_log(
                        db, robot_id, "WARNING",
                        f"Неизвестный тип робота: {robot.get('robot_type')}"
                    )
                    break

                # Ждем перед следующей итерацией
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"❌ Error in robot loop {robot_id}: {e}", exc_info=True)
                await self._handle_error(db, robot, str(e))
                await asyncio.sleep(60)

    async def _run_grid_strategy(self, db: Session, robot: dict, token: str):
        """Пример стратегии - сеточный робот"""
        try:
            # Получаем портфель для проверки баланса
            portfolio = await tinvest_service.get_portfolio_data(token)

            await self._add_log(
                db, robot["id"], "DEBUG",
                f"Grid strategy check. Portfolio: {portfolio['portfolio']['total_amount_portfolio']['decimal']}"
            )

        except Exception as e:
            await self._add_log(
                db, robot["id"], "ERROR",
                f"Error in grid strategy: {str(e)}"
            )
            raise

    async def _run_trend_strategy(self, db: Session, robot: dict, token: str):
        """Пример стратегии - трендовый робот"""
        try:
            await self._add_log(
                db, robot["id"], "DEBUG",
                "Trend strategy check"
            )
        except Exception as e:
            await self._add_log(
                db, robot["id"], "ERROR",
                f"Error in trend strategy: {str(e)}"
            )
            raise

    # === ТОРГОВЫЕ ОПЕРАЦИИ ===

    async def create_trade(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            trade_data: schemas.RobotTradeCreate
    ) -> dict:
        """Создание записи о сделке"""
        self.db = db

        # Проверяем робота
        robot = await self.get_robot_by_id(db, robot_id, user_id)

        now = datetime.now(timezone.utc)
        total_amount = trade_data.quantity * trade_data.price

        # Создаем сделку
        insert_query = queries.build_create_trade_query()
        result = self._execute(
            insert_query,
            {
                "robot_id": robot_id,
                "figi": trade_data.figi,
                "ticker": trade_data.ticker,
                "instrument_type": trade_data.instrument_type,
                "side": trade_data.side,
                "quantity": trade_data.quantity,
                "price": trade_data.price,
                "total_amount": total_amount,
                "order_id": trade_data.order_id,
                "status": "open",
                "created_at": now
            },
            fetch_one=True
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать сделку"
            )

        trade_id = result[0]

        # Обновляем статистику робота
        update_query = queries.build_update_robot_stats_after_trade_query()
        self._execute(
            update_query,
            {
                "robot_id": robot_id,
                "success_increment": 0,
                "profit": 0,
                "profit_percent": 0
            }
        )

        db.commit()

        await self._add_log(
            db, robot_id, "INFO",
            f"Сделка создана: {trade_data.side} {trade_data.quantity} {trade_data.ticker} по {trade_data.price}"
        )

        # Получаем созданную сделку
        return await self.get_trade_by_id(db, trade_id, user_id)

    async def close_trade(
            self,
            db: Session,
            trade_id: int,
            user_id: int,
            close_price: float
    ) -> dict:
        """Закрытие сделки"""
        self.db = db

        # Получаем сделку с проверкой робота
        trade_query = """
                      SELECT t.*, r.user_id
                      FROM ganaly.robot_trades t
                               JOIN ganaly.trading_robots r ON t.robot_id = r.id
                      WHERE t.id = :trade_id \
                      """

        trade_result = self._execute(
            trade_query,
            {"trade_id": trade_id},
            fetch_one=True
        )

        if not trade_result or trade_result[-1] != user_id:  # последнее поле - user_id
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Сделка не найдена"
            )

        # Преобразуем в словарь для удобства
        trade_dict = self._row_to_trade_dict(trade_result[:-1])  # без user_id

        if trade_dict.get("status") != "open":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Сделка уже закрыта"
            )

        # Рассчитываем прибыль
        if trade_dict["side"] == "buy":
            profit = (close_price - trade_dict["price"]) * trade_dict["quantity"]
        else:
            profit = (trade_dict["price"] - close_price) * trade_dict["quantity"]

        profit_percent = (profit / trade_dict["total_amount"]) * 100

        now = datetime.now(timezone.utc)

        # Закрываем сделку
        close_query = queries.build_close_trade_query()
        close_result = self._execute(
            close_query,
            {
                "trade_id": trade_id,
                "closed_at": now,
                "profit": profit,
                "profit_percent": profit_percent
            },
            fetch_one=True
        )

        if not close_result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось закрыть сделку"
            )

        robot_id = close_result[1]

        # Обновляем статистику робота
        update_query = queries.build_update_robot_stats_after_trade_query()
        self._execute(
            update_query,
            {
                "robot_id": robot_id,
                "success_increment": 1 if profit > 0 else 0,
                "profit": profit,
                "profit_percent": profit_percent
            }
        )

        db.commit()

        await self._add_log(
            db, robot_id, "INFO",
            f"Сделка закрыта: прибыль {profit:.2f} ({profit_percent:.2f}%)"
        )

        # Получаем обновленную сделку
        return await self.get_trade_by_id(db, trade_id, user_id)

    async def get_trade_by_id(self, db: Session, trade_id: int, user_id: int) -> Optional[dict]:
        """Получение сделки по ID с проверкой"""
        self.db = db

        query = """
                SELECT t.*
                FROM ganaly.robot_trades t
                         JOIN ganaly.trading_robots r ON t.robot_id = r.id
                WHERE t.id = :trade_id AND r.user_id = :user_id \
                """

        result = self._execute(
            query,
            {"trade_id": trade_id, "user_id": user_id},
            fetch_one=True
        )

        if not result:
            return None

        return self._row_to_trade_dict(result)

    async def get_robot_trades(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            limit: int = 100,
            status: Optional[str] = None
    ) -> List[dict]:
        """Получение списка сделок робота"""
        self.db = db

        # Проверяем робота
        await self.get_robot_by_id(db, robot_id, user_id)

        query, params = queries.build_get_robot_trades_query(
            robot_id=robot_id,
            limit=limit,
            status=status
        )

        results = self._execute(query, params).fetchall()

        trades = []
        for row in results:
            trades.append(self._row_to_trade_dict(row))

        return trades

    # === ЛОГИ ===

    async def _add_log(
            self,
            db: Session,
            robot_id: int,
            level: str,
            message: str,
            details: dict = None
    ):
        """Добавление лога"""
        self.db = db

        insert_query = queries.build_create_log_query()
        self._execute(
            insert_query,
            {
                "robot_id": robot_id,
                "level": level.upper(),
                "message": message,
                "details": json.dumps(details) if details else None,
                "created_at": datetime.now(timezone.utc)
            },
            fetch_one=False
        )
        db.commit()

    async def get_robot_logs(
            self,
            db: Session,
            robot_id: int,
            user_id: int,
            level: Optional[str] = None,
            limit: int = 100
    ) -> List[dict]:
        """Получение логов робота"""
        self.db = db

        # Проверяем робота
        await self.get_robot_by_id(db, robot_id, user_id)

        query, params = queries.build_get_robot_logs_query(
            robot_id=robot_id,
            level=level,
            limit=limit
        )

        results = self._execute(query, params).fetchall()

        logs = []
        for row in results:
            logs.append(self._row_to_log_dict(row))

        return logs

    # === СТАТИСТИКА ===

    async def get_robot_stats(self, db: Session, robot_id: int, user_id: int) -> dict:
        """Получение расширенной статистики робота"""
        self.db = db

        robot = await self.get_robot_by_id(db, robot_id, user_id)

        # Основная статистика
        stats_query, stats_params = queries.build_get_robot_stats_query(robot_id)
        stats = self._execute(stats_query, stats_params, fetch_one=True)

        # Статистика по дням
        daily_query, daily_params = queries.build_get_trades_by_day_query(robot_id)
        daily_results = self._execute(daily_query, daily_params).fetchall()

        # Последние сделки
        recent_trades = await self.get_robot_trades(db, robot_id, user_id, limit=100)

        # Формируем результат
        if stats:
            total_trades = self._safe_int(stats[0])
            successful = self._safe_int(stats[1])
            failed = self._safe_int(stats[2])
            success_rate = (successful / total_trades * 100) if total_trades > 0 else 0

            result = {
                "total_trades": total_trades,
                "successful_trades": successful,
                "failed_trades": failed,
                "success_rate": success_rate,
                "total_profit": self._safe_float(stats[6]),
                "average_profit_per_trade": self._safe_float(stats[3]),
                "biggest_win": self._safe_float(stats[4]),
                "biggest_loss": self._safe_float(stats[5]),
                "last_trade_at": stats[7],
                "active_since": robot.get("started_at"),
                "trades_by_day": [],
                "profit_by_day": {},
                "recent_trades": recent_trades[:10]
            }

            # Добавляем статистику по дням
            for day_row in daily_results:
                day_str = str(day_row[0])
                result["trades_by_day"].append({
                    "date": day_str,
                    "count": self._safe_int(day_row[1]),
                    "profit": self._safe_float(day_row[2])
                })
                result["profit_by_day"][day_str] = self._safe_float(day_row[2])

            return result

        return {
            "total_trades": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "success_rate": 0,
            "total_profit": 0,
            "average_profit_per_trade": 0,
            "biggest_win": 0,
            "biggest_loss": 0,
            "last_trade_at": None,
            "active_since": robot.get("started_at"),
            "trades_by_day": [],
            "profit_by_day": {},
            "recent_trades": []
        }

    async def _handle_error(self, db: Session, robot: dict, error: str):
        """Обработка ошибки робота"""
        now = datetime.now(timezone.utc)

        # Обновляем статус
        update_query, _ = queries.build_update_robot_query(["status", "is_active", "last_error", "last_error_at"])

        self._execute(
            update_query,
            {
                "robot_id": robot["id"],
                "user_id": robot["user_id"],
                "status": "error",
                "is_active": 0,
                "last_error": error,
                "last_error_at": now,
                "now": now
            }
        )
        db.commit()

        await self._add_log(db, robot["id"], "ERROR", error)
        logger.error(f"❌ Robot {robot['id']} error: {error}")

    # === ЗАДАЧИ ДЛЯ ПЛАНИРОВЩИКА ===

    async def run_all_due_updates(self) -> Dict[str, Any]:
        """
        Запускается scheduler'ом - обновляет портфели для всех активных токенов,
        которые требуют обновления (учитывая refresh_interval_minutes)
        """
        from app.core.database import SessionLocal
        from app.modules.robots.portfolio_updater.robot import PortfolioUpdaterRobot  # ← ИСПРАВЛЕНО
        from app.modules.robots.portfolio_updater.scheduler import PortfolioUpdaterScheduler  # ← ИСПРАВЛЕНО

        db = SessionLocal()
        self.db = db

        results = {
            "total": 0,
            "checked": 0,
            "skipped": 0,
            "updated": 0,
            "errors": [],
            "error": None
        }

        try:
            # Создаем планировщик для обновления
            scheduler = PortfolioUpdaterScheduler()
            scheduler.robot.db = db

            # Получаем токены, которые требуют обновления
            tokens_needing_update = await scheduler.get_tokens_for_update(db)

            results["total"] = len(tokens_needing_update)
            logger.info(f"🔄 Portfolio updater found {len(tokens_needing_update)} tokens that need update")

            # Для каждого токена запускаем обновление
            for token_info in tokens_needing_update:
                try:
                    token_id = token_info["id"]
                    user_id = token_info["user_id"]
                    token = token_info["token"]

                    # Создаем отдельного робота для каждого токена
                    robot = PortfolioUpdaterRobot(f"auto_{token_id}")
                    robot.db = db

                    result = await robot.run(
                        user_id=user_id,
                        token_id=token_id,
                        token=token
                    )

                    results["checked"] += 1

                    if result.get("status") == "skipped":
                        results["skipped"] += 1
                        logger.info(f"⏭️ Token {token_id}: skipped (interval not reached)")
                    elif result.get("status") == "success":
                        results["updated"] += 1
                        logger.info(f"✅ Token {token_id}: "
                                    f"accounts: {result.get('accounts_found', 0)}, "
                                    f"snapshots: {result.get('snapshots_saved', 0)}")
                    else:
                        results["errors"].append({
                            "token_id": token_id,
                            "error": result.get("error", "Unknown error")
                        })

                except Exception as e:
                    error_result = {
                        "token_id": token_info["id"],
                        "user_id": token_info["user_id"],
                        "error": str(e)
                    }
                    results["errors"].append(error_result)
                    logger.error(f"❌ Token {token_info['id']} failed: {e}")

            logger.info(f"📊 Update summary: "
                        f"total={results['total']}, "
                        f"updated={results['updated']}, "
                        f"skipped={results['skipped']}, "
                        f"errors={len(results['errors'])}")

            return results

        except Exception as e:
            logger.error(f"❌ Portfolio updater error: {e}")
            results["error"] = str(e)
            return results
        finally:
            db.close()


# Создаем экземпляр сервиса
robot_service = RobotService()