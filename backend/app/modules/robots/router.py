from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
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

@router.get("", response_model=schemas.RobotListResponse)
async def get_robots(
        include_inactive: bool = Query(False, description="Включить неактивных роботов"),
        robot_type: Optional[str] = Query(None, description="Фильтр по типу робота"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Получение списка всех роботов пользователя"""
    robots = await service.robot_service.get_user_robots(
        db,
        current_user.id,
        include_inactive,
        robot_type
    )

    return schemas.RobotListResponse(
        total=len(robots),
        items=[schemas.RobotInDB.model_validate(r) for r in robots]
    )


@router.get("/{robot_id}", response_model=schemas.RobotInDB)
async def get_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Получение информации о конкретном роботе"""
    robot = await service.robot_service.get_robot_by_id(db, robot_id, current_user.id)
    return schemas.RobotInDB.model_validate(robot)


@router.post("", response_model=schemas.RobotInDB, status_code=status.HTTP_201_CREATED)
async def create_robot(
        robot_data: schemas.RobotCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Создание нового робота"""
    robot = await service.robot_service.create_robot(db, current_user.id, robot_data)
    return schemas.RobotInDB.model_validate(robot)


@router.patch("/{robot_id}", response_model=schemas.RobotInDB)
async def update_robot(
        robot_id: int,
        robot_data: schemas.RobotUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Обновление параметров робота"""
    robot = await service.robot_service.update_robot(db, robot_id, current_user.id, robot_data)
    return schemas.RobotInDB.model_validate(robot)


@router.delete("/{robot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Удаление робота"""
    await service.robot_service.delete_robot(db, robot_id, current_user.id)
    return None


# === УПРАВЛЕНИЕ СОСТОЯНИЕМ ===

@router.post("/{robot_id}/start", response_model=schemas.RobotInDB)
async def start_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Запуск робота"""
    robot = await service.robot_service.start_robot(db, robot_id, current_user.id)
    return schemas.RobotInDB.model_validate(robot)


@router.post("/{robot_id}/stop", response_model=schemas.RobotInDB)
async def stop_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Остановка робота"""
    robot = await service.robot_service.stop_robot(db, robot_id, current_user.id)
    return schemas.RobotInDB.model_validate(robot)


# === СПЕЦИАЛЬНЫЕ ЭНДПОИНТЫ ДЛЯ РАЗНЫХ ТИПОВ РОБОТОВ ===

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
                           WHERE user_id = :user_id AND is_active = 1 \
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

@router.get("/logs", response_model=schemas.RobotLogListResponse)
async def get_robot_logs(
        robot_name: Optional[str] = Query(None, description="Фильтр по имени робота"),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Получение логов роботов
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