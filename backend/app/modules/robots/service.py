from typing import Optional, List, Dict, Any
import logging
from datetime import datetime, timezone
import asyncio

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from fastapi import HTTPException, status

from app.modules.robots.models import TradingRobot, RobotTrade, RobotLog, RobotSignal
from app.modules.tinvest.token_service import token_service
from app.modules.tinvest.service import tinvest_service
from app.modules.robots.schemas import RobotCreate, RobotUpdate, RobotTradeCreate

logger = logging.getLogger(__name__)


class RobotService:
    """Сервис для управления торговыми роботами"""

    # --- Управление роботами ---

    @staticmethod
    async def get_user_robots(
            db: Session,
            user_id: int,
            include_inactive: bool = False,
            robot_type: Optional[str] = None
    ) -> List[TradingRobot]:
        """Получение всех роботов пользователя"""
        query = db.query(TradingRobot).filter(TradingRobot.user_id == user_id)

        if not include_inactive:
            query = query.filter(TradingRobot.is_active == 1)

        if robot_type:
            query = query.filter(TradingRobot.robot_type == robot_type)

        return query.order_by(desc(TradingRobot.created_at)).all()

    @staticmethod
    async def get_robot_by_id(db: Session, robot_id: int, user_id: int) -> TradingRobot:
        """Получение робота по ID (с проверкой владельца)"""
        robot = db.query(TradingRobot).filter(
            TradingRobot.id == robot_id,
            TradingRobot.user_id == user_id
        ).first()

        if not robot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Робот не найден"
            )

        return robot

    @staticmethod
    async def create_robot(
            db: Session,
            user_id: int,
            robot_data: RobotCreate
    ) -> TradingRobot:
        """Создание нового робота"""
        # Проверяем токен, если указан
        if robot_data.token_id:
            token = await token_service.get_token_by_id(db, robot_data.token_id, user_id)
            if not token.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Выбранный токен не активен"
                )

        # Создаем робота
        robot = TradingRobot(
            user_id=user_id,
            token_id=robot_data.token_id,
            name=robot_data.name,
            description=robot_data.description,
            robot_type=robot_data.robot_type,
            strategy_params=robot_data.strategy_params or {},
            max_daily_loss=robot_data.max_daily_loss,
            max_position_size=robot_data.max_position_size,
            allowed_instruments=robot_data.allowed_instruments,
            status="stopped",
            is_active=0,
            created_at=datetime.now(timezone.utc)
        )

        db.add(robot)
        db.commit()
        db.refresh(robot)

        await RobotService._add_log(db, robot.id, "INFO", f"Робот '{robot.name}' создан")
        logger.info(f"✅ Created robot {robot.id} for user {user_id}")

        return robot

    @staticmethod
    async def update_robot(
            db: Session,
            robot_id: int,
            user_id: int,
            robot_data: RobotUpdate
    ) -> TradingRobot:
        """Обновление робота"""
        robot = await RobotService.get_robot_by_id(db, robot_id, user_id)

        # Если робот активен, запрещаем некоторые изменения
        if robot.status == "active":
            forbidden_fields = ["token_id", "strategy_params", "max_daily_loss", "max_position_size"]
            changes = robot_data.model_dump(exclude_unset=True)
            if any(field in changes for field in forbidden_fields):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Нельзя изменять параметры стратегии у активного робота. Сначала остановите робота."
                )

        # Проверяем токен, если меняется
        if robot_data.token_id is not None and robot_data.token_id != robot.token_id:
            token = await token_service.get_token_by_id(db, robot_data.token_id, user_id)
            if not token.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Выбранный токен не активен"
                )
            robot.token_id = robot_data.token_id

        # Обновляем поля
        update_data = robot_data.model_dump(exclude_unset=True, exclude={"token_id"})
        for field, value in update_data.items():
            setattr(robot, field, value)

        robot.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(robot)

        await RobotService._add_log(db, robot.id, "INFO", f"Робот '{robot.name}' обновлен")
        logger.info(f"✅ Updated robot {robot_id} for user {user_id}")

        return robot

    @staticmethod
    async def delete_robot(db: Session, robot_id: int, user_id: int):
        """Удаление робота"""
        robot = await RobotService.get_robot_by_id(db, robot_id, user_id)

        if robot.status == "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя удалить активного робота. Сначала остановите робота."
            )

        db.delete(robot)
        db.commit()

        logger.info(f"✅ Deleted robot {robot_id} for user {user_id}")

    # --- Управление состоянием робота ---

    @staticmethod
    async def start_robot(db: Session, robot_id: int, user_id: int) -> TradingRobot:
        """Запуск робота"""
        robot = await RobotService.get_robot_by_id(db, robot_id, user_id)

        # Проверяем наличие токена
        if not robot.token_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для запуска робота необходимо выбрать токен доступа"
            )

        # Проверяем активность токена
        token = await token_service.get_token_by_id(db, robot.token_id, user_id)
        if not token.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Выбранный токен не активен"
            )

        # Меняем статус
        robot.status = "active"
        robot.is_active = 1
        robot.started_at = datetime.now(timezone.utc)
        robot.stopped_at = None
        robot.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(robot)

        await RobotService._add_log(db, robot.id, "INFO", f"Робот '{robot.name}' запущен")
        logger.info(f"✅ Started robot {robot_id} for user {user_id}")

        # Запускаем основной цикл робота в фоне
        asyncio.create_task(RobotService._run_robot_loop(db, robot.id, user_id))

        return robot

    @staticmethod
    async def stop_robot(db: Session, robot_id: int, user_id: int) -> TradingRobot:
        """Остановка робота"""
        robot = await RobotService.get_robot_by_id(db, robot_id, user_id)

        robot.status = "stopped"
        robot.is_active = 0
        robot.stopped_at = datetime.now(timezone.utc)
        robot.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(robot)

        await RobotService._add_log(db, robot.id, "INFO", f"Робот '{robot.name}' остановлен")
        logger.info(f"✅ Stopped robot {robot_id} for user {user_id}")

        return robot

    # --- Основной цикл робота ---

    @staticmethod
    async def _run_robot_loop(db: Session, robot_id: int, user_id: int):
        """Основной цикл работы робота (запускается в фоне)"""
        logger.info(f"🔄 Starting robot loop for robot {robot_id}")

        while True:
            try:
                # Получаем актуальное состояние робота
                robot = await RobotService.get_robot_by_id(db, robot_id, user_id)

                # Если робот остановлен, выходим из цикла
                if robot.status != "active":
                    logger.info(f"⏹️ Robot {robot_id} is not active, stopping loop")
                    break

                # Получаем токен
                token = await token_service.get_token_by_id(db, robot.token_id, user_id)
                if not token or not token.is_active:
                    await RobotService._handle_error(db, robot, "Токен не активен")
                    break

                # Здесь будет логика конкретного робота в зависимости от типа
                if robot.robot_type == "grid":
                    await RobotService._run_grid_strategy(db, robot, token.token)
                elif robot.robot_type == "trend":
                    await RobotService._run_trend_strategy(db, robot, token.token)
                else:
                    await RobotService._add_log(
                        db, robot.id, "WARNING",
                        f"Неизвестный тип робота: {robot.robot_type}"
                    )
                    break

                # Ждем перед следующей итерацией
                await asyncio.sleep(60)  # Проверка раз в минуту

            except Exception as e:
                logger.error(f"❌ Error in robot loop {robot_id}: {e}", exc_info=True)
                await RobotService._handle_error(db, robot, str(e))
                await asyncio.sleep(60)

    @staticmethod
    async def _run_grid_strategy(db: Session, robot: TradingRobot, token: str):
        """Пример стратегии - сеточный робот"""
        try:
            # Получаем портфель для проверки баланса
            portfolio = await tinvest_service.get_portfolio_data(token)

            # Логика сеточной стратегии
            await RobotService._add_log(
                db, robot.id, "DEBUG",
                f"Grid strategy check. Portfolio: {portfolio['portfolio']['total_amount_portfolio']['decimal']}"
            )

            # Здесь будет реальная логика...

        except Exception as e:
            await RobotService._add_log(
                db, robot.id, "ERROR",
                f"Error in grid strategy: {str(e)}"
            )
            raise

    @staticmethod
    async def _run_trend_strategy(db: Session, robot: TradingRobot, token: str):
        """Пример стратегии - трендовый робот"""
        try:
            await RobotService._add_log(
                db, robot.id, "DEBUG",
                "Trend strategy check"
            )
            # Здесь будет реальная логика...

        except Exception as e:
            await RobotService._add_log(
                db, robot.id, "ERROR",
                f"Error in trend strategy: {str(e)}"
            )
            raise

    # --- Вспомогательные методы ---

    @staticmethod
    async def _handle_error(db: Session, robot: TradingRobot, error: str):
        """Обработка ошибки робота"""
        robot.status = "error"
        robot.is_active = 0
        robot.last_error = error
        robot.last_error_at = datetime.now(timezone.utc)
        robot.stopped_at = datetime.now(timezone.utc)
        db.commit()

        await RobotService._add_log(db, robot.id, "ERROR", error)
        logger.error(f"❌ Robot {robot.id} error: {error}")

    @staticmethod
    async def _add_log(db: Session, robot_id: int, level: str, message: str, details: dict = None):
        """Добавление лога"""
        log = RobotLog(
            robot_id=robot_id,
            level=level,
            message=message,
            details=details,
            created_at=datetime.now(timezone.utc)
        )
        db.add(log)
        db.commit()

    # --- Торговые операции ---

    @staticmethod
    async def create_trade(
            db: Session,
            robot_id: int,
            user_id: int,
            trade_data: RobotTradeCreate
    ) -> RobotTrade:
        """Создание записи о сделке"""
        robot = await RobotService.get_robot_by_id(db, robot_id, user_id)

        trade = RobotTrade(
            robot_id=robot_id,
            figi=trade_data.figi,
            ticker=trade_data.ticker,
            instrument_type=trade_data.instrument_type,
            side=trade_data.side,
            quantity=trade_data.quantity,
            price=trade_data.price,
            total_amount=trade_data.quantity * trade_data.price,
            order_id=trade_data.order_id,
            status="open",
            created_at=datetime.now(timezone.utc)
        )

        db.add(trade)
        db.commit()
        db.refresh(trade)

        # Обновляем статистику робота
        robot.total_trades += 1
        db.commit()

        await RobotService._add_log(
            db, robot_id, "INFO",
            f"Сделка создана: {trade_data.side} {trade_data.quantity} {trade_data.ticker} по {trade_data.price}"
        )

        return trade

    @staticmethod
    async def close_trade(
            db: Session,
            trade_id: int,
            user_id: int,
            close_price: float
    ) -> RobotTrade:
        """Закрытие сделки"""
        trade = db.query(RobotTrade).join(TradingRobot).filter(
            RobotTrade.id == trade_id,
            TradingRobot.user_id == user_id
        ).first()

        if not trade:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Сделка не найдена"
            )

        if trade.status != "open":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Сделка уже закрыта"
            )

        # Рассчитываем прибыль
        if trade.side == "buy":
            profit = (close_price - trade.price) * trade.quantity
        else:
            profit = (trade.price - close_price) * trade.quantity

        profit_percent = (profit / (trade.price * trade.quantity)) * 100

        trade.status = "closed"
        trade.closed_at = datetime.now(timezone.utc)
        trade.profit = profit
        trade.profit_percent = profit_percent

        db.commit()
        db.refresh(trade)

        # Обновляем статистику робота
        robot = trade.robot
        if profit > 0:
            robot.successful_trades += 1
        robot.total_profit += profit
        robot.total_profit_percent += profit_percent
        db.commit()

        await RobotService._add_log(
            db, robot.id, "INFO",
            f"Сделка закрыта: прибыль {profit:.2f} ({profit_percent:.2f}%)"
        )

        return trade

    # --- Статистика ---

    @staticmethod
    async def get_robot_stats(db: Session, robot_id: int, user_id: int) -> dict:
        """Получение расширенной статистики робота"""
        robot = await RobotService.get_robot_by_id(db, robot_id, user_id)

        # Получаем последние сделки
        recent_trades = db.query(RobotTrade).filter(
            RobotTrade.robot_id == robot_id
        ).order_by(desc(RobotTrade.created_at)).limit(100).all()

        # Группировка по дням
        from sqlalchemy import func, cast, Date
        trades_by_day = db.query(
            cast(RobotTrade.created_at, Date).label('day'),
            func.count().label('count'),
            func.sum(RobotTrade.profit).label('profit')
        ).filter(
            RobotTrade.robot_id == robot_id,
            RobotTrade.status == "closed"
        ).group_by(
            cast(RobotTrade.created_at, Date)
        ).order_by(
            cast(RobotTrade.created_at, Date).desc()
        ).limit(30).all()

        return {
            "robot": robot,
            "recent_trades": recent_trades,
            "trades_by_day": [
                {"date": str(day), "count": count, "profit": float(profit or 0)}
                for day, count, profit in trades_by_day
            ],
            "success_rate": (robot.successful_trades / robot.total_trades * 100) if robot.total_trades > 0 else 0
        }


# Создаем экземпляр сервиса
robot_service = RobotService()