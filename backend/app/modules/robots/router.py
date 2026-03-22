from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
import logging

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from . import schemas, service, queries
from .scheduler import scheduler
from .portfolio_updater.robot import PortfolioUpdaterRobot
from .common.logger import get_logger

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/robots", tags=["Trading Robots"])

# app/modules/robots/router.py

# === ПРОСМОТР РОБОТА ===

@router.post("/data", response_model=schemas.RobotListResponse)
async def get_robots(
        request: schemas.RobotListRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение списка всех роботов пользователя
    """

    # Строим запрос для получения данных
    query, params = queries.build_get_user_robots_query(
        robot_status=request.robot_status,
        robot_type=request.robot_type,
        robot_name=request.robot_name,
        token_type=request.token_type,
        limit=request.limit,
        offset=request.offset,
        sort_by=request.sort_by,
        sort_order=request.sort_order
    )
    params["user_id"] = current_user.id

    # Выполняем запрос
    result = db.execute(text(query), params).fetchall()

    # Строим запрос для подсчета общего количества
    count_query, count_params = queries.build_count_user_robots_query(
        robot_status=request.robot_status,
        robot_type=request.robot_type,
        robot_name=request.robot_name,
        token_type=request.token_type
    )
    count_params["user_id"] = current_user.id
    total = db.execute(text(count_query), count_params).scalar() or 0

    robots = []
    for row in result:
        robot_dict = {
            "id": row[0],
            "user_id": row[1],
            "token": {
                "id": row[2],
                "name": row[3],
                "status": row[4],
                "type": row[5],
                "typeName": row[6]
            },
            "name": row[7],
            "type": row[8],
            "typeName": row[9],
            "status": row[10],
            "statusName": row[11],
            "config": row[12] if row[12] is not None else {},
            "last_started": row[13],
            "last_error": row[14],
            "last_error_at": row[15],
            "last_stopped": row[16],
            "usercre": row[17],
            "date_creation": row[18],
            "usermod": row[19],
            "date_modification": row[20]
        }
        robots.append(robot_dict)

    return schemas.RobotListResponse(
        total=total,
        items=robots,
        limit=request.limit,
        offset=request.offset
    )

# === ИЗМЕНЕНИЕ РОБОТА ===

@router.post("/create", response_model=schemas.RobotInDB, status_code=status.HTTP_201_CREATED)
async def create_robot(
        robot_data: schemas.RobotCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Создание нового робота

    - **name**: Название робота (обязательно)
    - **type**: Тип робота (1 - Portfolio, 2 - Trading)
    - **token_id**: ID токена доступа
    """
    logger.info(f"🤖 Creating robot for user {current_user.id}")
    logger.info(f"📦 Received data: {robot_data}")

    # Валидация
    if robot_data.type not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Тип робота должен быть 1 (Portfolio) или 2 (Trading)"
        )

    try:
        robot = await service.robot_service.create_robot(db, current_user.id, robot_data)
        logger.info(f"✅ Robot created successfully: {robot['id']}")
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating robot: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании робота: {str(e)}"
        )



@router.post("/change_status", response_model=schemas.RobotInDB)
async def change_robot_status(
        request: schemas.ChangeStatusRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):

    if request.status not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Статус должен быть 1 (Включить) или 2 (Выключить)"
        )

    try:
        robot = await service.robot_service.change_robot_status(
            db,
            request.robotId,
            current_user.id,
            request.status
        )
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при изменении статуса робота: {str(e)}"
        )



#
# @router.get("/data/{robot_id}", response_model=schemas.RobotInDB)
# async def get_robot(
#         robot_id: int,
#         db: Session = Depends(get_db),
#         current_user: User = Depends(get_current_user)
# ):
#     """
#     Получение информации о конкретном роботе
#     """
#     robot = await service.robot_service.get_robot_by_id(db, robot_id, current_user.id)
#     return schemas.RobotInDB.model_validate(robot)
#
# @router.post("/update/{robot_id}", response_model=schemas.RobotInDB)
# async def update_robot(
#         robot_id: int,
#         robot_data: schemas.RobotUpdate,
#         db: Session = Depends(get_db),
#         current_user: User = Depends(get_current_user)
# ):
#     """
#     Обновление параметров робота
#     """
#     robot = await service.robot_service.update_robot(db, robot_id, current_user.id, robot_data)
#     return schemas.RobotInDB.model_validate(robot)
#
#
# @router.post("/delete/{robot_id}", status_code=status.HTTP_200_OK)
# async def delete_robot(
#         robot_id: int,
#         db: Session = Depends(get_db),
#         current_user: User = Depends(get_current_user)
# ):
#     """
#     Удаление (деактивация) робота
#     """
#     await service.robot_service.delete_robot(db, robot_id, current_user.id)
#     return {"message": "Robot successfully deleted", "success": True}



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



@router.get("/types")
async def get_robot_types(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение списка доступных типов роботов из справочника
    """
    query = """
            SELECT
                id,
                num_value,
                name,
                description,
                hide_from_ui
            FROM ganaly.dictionary
            WHERE table_name = 'ROBOT'
              AND column_name = 'TYPE'
              AND hide_from_ui = 0
            ORDER BY num_value \
            """

    result = db.execute(text(query)).fetchall()

    types = []
    for row in result:
        types.append({
            "id": row[0],
            "num_value": row[1],
            "name": row[2],
            "description": row[3],
            "hide_from_ui": row[4]
        })

    return types