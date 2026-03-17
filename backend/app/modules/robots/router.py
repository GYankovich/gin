from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
import logging

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from . import schemas, service
from .scheduler import scheduler
from .portfolio_updater.robot import PortfolioUpdaterRobot
from .common.logger import get_logger

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/robots", tags=["Trading Robots"])


# === УПРАВЛЕНИЕ РОБОТАМИ ===

@router.post("/data", response_model=schemas.RobotListResponse)
async def get_robots(
        request: schemas.RobotListRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение списка всех роботов пользователя
    Фильтрация по статусу и типу
    """
    logger.info(f"📊 Getting robots for user {current_user.id}")

    # Получаем ID статуса "Включен" из справочника
    status_active_id = db.execute(
        text("""
             SELECT id FROM ganaly.dictionary
             WHERE table_name = 'ROBOT'
               AND column_name = 'STATUS'
               AND num_value = 1
             """)
    ).scalar()

    # Базовый запрос
    query = """
            SELECT
                r.id,
                r.user_id,
                r.token_id,
                r.name,
                r.type as type_id,
                dt.name as type_name,
                dt.num_value as type_value,
                r.status as status_id,
                ds.name as status_name,
                ds.num_value as status_value,
                r.config,
                r.last_started,
                r.last_error,
                r.last_error_at,
                r.usercre,
                r.date_creation,
                r.usermod,
                r.date_modification
            FROM ganaly.robots r
                     LEFT JOIN ganaly.dictionary dt ON r.type = dt.id AND dt.table_name = 'ROBOT' AND dt.column_name = 'TYPE'
                     LEFT JOIN ganaly.dictionary ds ON r.status = ds.id AND ds.table_name = 'ROBOT' AND ds.column_name = 'STATUS'
            WHERE r.user_id = :user_id \
            """

    params = {"user_id": current_user.id}

    # Фильтр по статусу (только активные, если не запрошены неактивные)
    if not request.include_inactive:
        query += " AND r.status = :status_active_id"
        params["status_active_id"] = status_active_id

    # Фильтр по типу робота
    if request.robot_type:
        # Получаем ID типа робота из справочника
        type_id = db.execute(
            text("""
                 SELECT id FROM ganaly.dictionary
                 WHERE table_name = 'ROBOT'
                   AND column_name = 'TYPE'
                   AND num_value = :type_value
                 """),
            {"type_value": request.robot_type}
        ).scalar()

        if type_id:
            query += " AND r.type = :type_id"
            params["type_id"] = type_id

    query += " ORDER BY r.date_creation DESC"

    # Выполняем запрос
    result = db.execute(text(query), params).fetchall()

    # Формируем ответ
    robots = []
    for row in result:
        robot_dict = {
            "id": row[0],
            "user_id": row[1],
            "token_id": row[2],
            "name": row[3],
            "type": {
                "id": row[4],
                "name": row[5],
                "value": row[6]
            },
            "status": {
                "id": row[7],
                "name": row[8],
                "value": row[9]
            },
            "config": row[10] or {},
            "last_started": row[11],
            "last_error": row[12],
            "last_error_at": row[13],
            "usercre": row[14],
            "date_creation": row[15],
            "usermod": row[16],
            "date_modification": row[17]
        }
        robots.append(robot_dict)

    logger.info(f"✅ Found {len(robots)} robots for user {current_user.id}")

    return schemas.RobotListResponse(
        total=len(robots),
        items=robots
    )


@router.get("/data/{robot_id}", response_model=schemas.RobotInDB)
async def get_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение информации о конкретном роботе
    """
    robot = await service.robot_service.get_robot_by_id(db, robot_id, current_user.id)
    return schemas.RobotInDB.model_validate(robot)


@router.post("/create", response_model=schemas.RobotInDB, status_code=status.HTTP_201_CREATED)
async def create_robot(
        robot_data: schemas.RobotCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Создание нового робота
    """
    robot = await service.robot_service.create_robot(db, current_user.id, robot_data)
    return schemas.RobotInDB.model_validate(robot)


@router.post("/update/{robot_id}", response_model=schemas.RobotInDB)
async def update_robot(
        robot_id: int,
        robot_data: schemas.RobotUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Обновление параметров робота
    """
    robot = await service.robot_service.update_robot(db, robot_id, current_user.id, robot_data)
    return schemas.RobotInDB.model_validate(robot)


@router.post("/delete/{robot_id}", status_code=status.HTTP_200_OK)
async def delete_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Удаление (деактивация) робота
    """
    await service.robot_service.delete_robot(db, robot_id, current_user.id)
    return {"message": "Robot successfully deleted", "success": True}


# === УПРАВЛЕНИЕ СОСТОЯНИЕМ ===

@router.post("/{robot_id}/start", response_model=schemas.RobotInDB)
async def start_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Запуск робота
    """
    robot = await service.robot_service.start_robot(db, robot_id, current_user.id)
    return schemas.RobotInDB.model_validate(robot)


@router.post("/{robot_id}/stop", response_model=schemas.RobotInDB)
async def stop_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Остановка робота
    """
    robot = await service.robot_service.stop_robot(db, robot_id, current_user.id)
    return schemas.RobotInDB.model_validate(robot)


# === СТРАТЕГИИ ===

@router.post("/trading/strategies")
async def list_trading_strategies():
    """
    Список доступных торговых стратегий
    """
    from .trading.strategies import list_strategies
    return list_strategies()


@router.get("/trading/strategies/{name}")
async def get_strategy_info_endpoint(name: str):
    """
    Информация о конкретной стратегии
    """
    from .trading.strategies import get_strategy_info
    info = get_strategy_info(name)
    if not info:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return info


# === СПЕЦИАЛЬНЫЕ ЭНДПОИНТЫ ===

@router.post("/portfolio-updater/run")
async def run_portfolio_updater(
        token_id: Optional[int] = Query(None, description="ID токена для обновления"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Ручной запуск робота обновления портфеля
    """
    try:
        if token_id:
            # Проверяем, что токен принадлежит пользователю
            token_query = "SELECT token FROM ganaly.api_tokens WHERE id = :id AND user_id = :user_id AND is_active = 1"
            token = db.execute(
                text(token_query),
                {"id": token_id, "user_id": current_user.id}
            ).first()

            if not token:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Токен не найден или неактивен"
                )

            # Запускаем робота
            robot = PortfolioUpdaterRobot(f"manual_{current_user.id}")
            robot.db = db

            result = await robot.run(
                user_id=current_user.id,
                token_id=token_id,
                token=token[0]
            )

            return {
                "success": True,
                "result": result
            }
        else:
            # Запускаем для всех токенов пользователя
            tokens_query = """
                           SELECT id, token FROM ganaly.api_tokens
                           WHERE user_id = :user_id AND is_active = 1
                           """
            tokens = db.execute(text(tokens_query), {"user_id": current_user.id}).fetchall()

            results = []
            for token_row in tokens:
                robot = PortfolioUpdaterRobot(f"manual_{current_user.id}")
                robot.db = db

                result = await robot.run(
                    user_id=current_user.id,
                    token_id=token_row[0],
                    token=token_row[1]
                )
                results.append({
                    "token_id": token_row[0],
                    "result": result
                })

            return {
                "success": True,
                "total": len(results),
                "results": results
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running portfolio updater: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при запуске: {str(e)}"
        )


# === СДЕЛКИ ===

@router.get("/{robot_id}/trades", response_model=List[schemas.RobotTradeInDB])
async def get_robot_trades(
        robot_id: int,
        limit: int = Query(100, ge=1, le=1000),
        status: Optional[str] = Query(None, description="Фильтр по статусу сделки"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение списка сделок робота
    """
    trades = await service.robot_service.get_robot_trades(
        db,
        robot_id,
        current_user.id,
        limit=limit,
        status=status
    )

    return [schemas.RobotTradeInDB.model_validate(t) for t in trades]


# === ЛОГИ ===

@router.get("/{robot_id}/logs", response_model=List[schemas.RobotLogInDB])
async def get_robot_logs(
        robot_id: int,
        level: Optional[str] = Query(None, description="Фильтр по уровню лога"),
        limit: int = Query(100, ge=1, le=1000),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение логов робота
    """
    logs = await service.robot_service.get_robot_logs(
        db,
        robot_id,
        current_user.id,
        level=level,
        limit=limit
    )

    return [schemas.RobotLogInDB.model_validate(l) for l in logs]


@router.get("/logs", response_model=schemas.RobotLogListResponse)
async def get_all_robot_logs(
        robot_name: Optional[str] = Query(None, description="Фильтр по имени робота"),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение логов всех роботов пользователя
    """
    from .queries import build_get_robot_logs_query

    query, params = build_get_robot_logs_query(
        robot_name=robot_name,
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )

    results = db.execute(text(query), params).fetchall()

    logs = []
    for row in results:
        logs.append({
            "id": row[0],
            "robot_name": row[1],
            "robot_version": row[2],
            "token_id": row[3],
            "user_id": row[4],
            "started_at": row[6],
            "finished_at": row[7],
            "duration_ms": row[8],
            "success": bool(row[9]),
            "error_message": row[10]
        })

    return {
        "total": len(logs),
        "logs": logs,
        "limit": limit,
        "offset": offset
    }


@router.get("/logs/stats")
async def get_robot_log_stats(
        db: Session = Depends(get_db)
):
    """
    Получение статистики по логам роботов
    """
    from .queries import build_get_robot_log_stats_query

    query = build_get_robot_log_stats_query()
    results = db.execute(text(query)).fetchall()

    stats = []
    for row in results:
        stats.append({
            "robot_name": row[0],
            "total_runs": row[1],
            "successful": row[2],
            "failed": row[3],
            "avg_duration_ms": row[4],
            "last_run": row[5]
        })

    return stats


# === СТАТИСТИКА ===

@router.get("/{robot_id}/stats", response_model=schemas.RobotStats)
async def get_robot_stats(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение расширенной статистики робота
    """
    stats = await service.robot_service.get_robot_stats(db, robot_id, current_user.id)
    return schemas.RobotStats.model_validate(stats)


# === УПРАВЛЕНИЕ ПЛАНИРОВЩИКОМ ===

@router.get("/scheduler/status")
async def get_scheduler_status():
    """
    Получение статуса планировщика
    """
    return {
        "running": scheduler.running,
        "next_check": "every 60 seconds"
    }


@router.post("/scheduler/force-update")
async def force_scheduler_update(
        token_id: Optional[int] = Query(None, description="ID токена для обновления"),
        db: Session = Depends(get_db)
):
    """
    Принудительный запуск обновления
    """
    try:
        result = await scheduler.force_update(db, token_id)
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# === ВРЕМЕННЫЙ ДЕБАГ-ЭНДПОИНТ ===

@router.get("/debug/tokens-to-update")
async def debug_tokens_to_update(
        db: Session = Depends(get_db)
):
    """
    Отладка - показывает какие токены требуют обновления
    """
    from .queries import build_get_tokens_for_update_query

    query = build_get_tokens_for_update_query()
    results = db.execute(text(query)).fetchall()

    tokens = []
    for row in results:
        tokens.append({
            "id": row[0],
            "user_id": row[1],
            "refresh_interval": row[3],
            "last_used_at": row[4],
            "created_at": row[5]
        })

    return {
        "total": len(tokens),
        "tokens": tokens
    }