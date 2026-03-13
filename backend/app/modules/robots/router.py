from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import logging

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from app.modules.tinvest.token_service import token_service
from .schemas import (
    RobotCreate, RobotUpdate, RobotInDB, RobotListResponse,
    RobotAction, RobotTradeCreate, RobotTradeInDB,
    RobotLogInDB, RobotSignalInDB, RobotStats
)
from .service import robot_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/robots", tags=["Trading Robots"])


# --- Управление роботами ---

@router.get("", response_model=RobotListResponse)
async def get_robots(
        include_inactive: bool = Query(False, description="Включить неактивных роботов"),
        robot_type: Optional[str] = Query(None, description="Фильтр по типу робота"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Получение списка всех роботов пользователя"""
    robots = await robot_service.get_user_robots(
        db,
        current_user.id,
        include_inactive,
        robot_type
    )

    # Подгружаем информацию о токенах
    for robot in robots:
        if robot.token_id:
            token = await token_service.get_token_by_id(db, robot.token_id, current_user.id)
            robot.token = token

    return RobotListResponse(
        total=len(robots),
        items=[RobotInDB.model_validate(r) for r in robots]
    )


@router.get("/{robot_id}", response_model=RobotInDB)
async def get_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Получение информации о конкретном роботе"""
    robot = await robot_service.get_robot_by_id(db, robot_id, current_user.id)

    if robot.token_id:
        token = await token_service.get_token_by_id(db, robot.token_id, current_user.id)
        robot.token = token

    return robot


@router.post("", response_model=RobotInDB, status_code=status.HTTP_201_CREATED)
async def create_robot(
        robot_data: RobotCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Создание нового торгового робота"""
    robot = await robot_service.create_robot(db, current_user.id, robot_data)

    if robot.token_id:
        token = await token_service.get_token_by_id(db, robot.token_id, current_user.id)
        robot.token = token

    return robot


@router.patch("/{robot_id}", response_model=RobotInDB)
async def update_robot(
        robot_id: int,
        robot_data: RobotUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Обновление параметров робота"""
    robot = await robot_service.update_robot(db, robot_id, current_user.id, robot_data)

    if robot.token_id:
        token = await token_service.get_token_by_id(db, robot.token_id, current_user.id)
        robot.token = token

    return robot


@router.delete("/{robot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Удаление робота"""
    await robot_service.delete_robot(db, robot_id, current_user.id)
    return None


# --- Управление состоянием ---

@router.post("/{robot_id}/start", response_model=RobotInDB)
async def start_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Запуск робота"""
    robot = await robot_service.start_robot(db, robot_id, current_user.id)

    if robot.token_id:
        token = await token_service.get_token_by_id(db, robot.token_id, current_user.id)
        robot.token = token

    return robot


@router.post("/{robot_id}/stop", response_model=RobotInDB)
async def stop_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Остановка робота"""
    robot = await robot_service.stop_robot(db, robot_id, current_user.id)

    if robot.token_id:
        token = await token_service.get_token_by_id(db, robot.token_id, current_user.id)
        robot.token = token

    return robot


@router.post("/{robot_id}/action")
async def robot_action(
        robot_id: int,
        action: RobotAction,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Выполнение действия с роботом (start/stop/pause/restart)"""
    if action.action == "start":
        robot = await robot_service.start_robot(db, robot_id, current_user.id)
    elif action.action == "stop":
        robot = await robot_service.stop_robot(db, robot_id, current_user.id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Действие {action.action} не поддерживается"
        )

    return {"status": "success", "robot_status": robot.status}


# --- Сделки и логи ---

@router.get("/{robot_id}/trades", response_model=List[RobotTradeInDB])
async def get_robot_trades(
        robot_id: int,
        limit: int = Query(100, ge=1, le=1000),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Получение списка сделок робота"""
    robot = await robot_service.get_robot_by_id(db, robot_id, current_user.id)

    trades = db.query(RobotTrade).filter(
        RobotTrade.robot_id == robot_id
    ).order_by(RobotTrade.created_at.desc()).limit(limit).all()

    return trades


@router.get("/{robot_id}/logs", response_model=List[RobotLogInDB])
async def get_robot_logs(
        robot_id: int,
        level: Optional[str] = Query(None, description="Фильтр по уровню лога"),
        limit: int = Query(100, ge=1, le=1000),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Получение логов робота"""
    robot = await robot_service.get_robot_by_id(db, robot_id, current_user.id)

    query = db.query(RobotLog).filter(RobotLog.robot_id == robot_id)

    if level:
        query = query.filter(RobotLog.level == level.upper())

    logs = query.order_by(RobotLog.created_at.desc()).limit(limit).all()

    return logs


@router.get("/{robot_id}/stats", response_model=RobotStats)
async def get_robot_stats(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Получение расширенной статистики робота"""
    return await robot_service.get_robot_stats(db, robot_id, current_user.id)


# --- Токены для роботов (дополнительный эндпоинт) ---

@router.get("/available-tokens", response_model=List[dict])
async def get_available_tokens(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Получение списка доступных токенов для привязки к роботам"""
    tokens = await token_service.get_user_tokens(db, current_user.id, include_inactive=False)

    return [
        {
            "id": t.id,
            "token_name": t.token_name,
            "token_preview": t.mask_token(),
            "last_used_at": t.last_used_at
        }
        for t in tokens
    ]