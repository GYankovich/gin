from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List

#///EPIC Backtesting.ITEM RobotsAPI.TOPIC Endpoints Map [1]
#/// REST-контракт модуля robots: CRUD, schedule/config, history-backtest, live snapshot,
#/// сравнение прогонов и вспомогательные операции по инструментам.
from app.core.database import get_db
from app.core.logging_config import get_logger
from app.core.config import settings
from app.core.security import get_current_user
from app.modules.auth.models import User
from . import schemas, service, queries
from .usecases import robot_backtest_usecase, robot_live_snapshot_usecase

logger = get_logger(__name__)
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
        sort_order=request.sort_order,
        schema=settings.DB_SCHEMA
    )
    params["user_id"] = current_user.id

    # Выполняем запрос
    result = db.execute(text(query), params).fetchall()

    # Строим запрос для подсчета общего количества
    count_query, count_params = queries.build_count_user_robots_query(
        robot_status=request.robot_status,
        robot_type=request.robot_type,
        robot_name=request.robot_name,
        token_type=request.token_type,
        schema=settings.DB_SCHEMA
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

    # Валидация
    if robot_data.type not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поддерживаются только роботы: 1 (опросник), 2 (торговый)"
        )

    try:
        robot = await service.robot_service.create_robot(db, current_user.id, robot_data)
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании робота: {str(e)}"
        )



@router.get("/id/{robot_id}", response_model=schemas.RobotInDB)
async def get_robot(
        robot_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    return schemas.RobotInDB.model_validate(
        await service.robot_service.get_robot_by_id(db, robot_id, current_user.id)
    )


@router.post("/update", response_model=schemas.RobotInDB)
async def update_robot(
        request: schemas.RobotUpdateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    try:
        robot = await service.robot_service.update_robot(
            db=db,
            robot_id=request.robotId,
            user_id=current_user.id,
            patch=request.patch
        )
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении робота: {str(e)}"
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


@router.post("/delete")
async def delete_robot(
        request: schemas.RobotIdRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Мягкое удаление робота (status=0)"""
    try:
        result = await service.robot_service.delete_robot(db, request.robotId, current_user.id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при удалении робота: {str(e)}"
        )


@router.get("/strategies", response_model=schemas.StrategyListResponse)
async def get_strategies(
        current_user: User = Depends(get_current_user)
):
    """Список стратегий и схем параметров для динамической формы на фронтенде."""
    items = await service.robot_service.get_available_strategies()
    return schemas.StrategyListResponse(items=items)


@router.get("/strategies/{name}", response_model=schemas.StrategyInfoResponse)
async def get_strategy_info(
        name: str,
        current_user: User = Depends(get_current_user)
):
    """Детальная информация по конкретной стратегии."""
    return await service.robot_service.get_strategy_info(name)


@router.post("/config", response_model=schemas.RobotInDB)
async def update_robot_config(
        request: schemas.RobotConfigUpdateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Обновление конфигурации робота."""
    try:
        robot = await service.robot_service.update_robot_config(
            db=db,
            robot_id=request.robotId,
            user_id=current_user.id,
            config=request.config.model_dump(),
        )
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении конфигурации: {str(e)}"
        )


@router.post("/schedule", response_model=schemas.RobotInDB)
async def update_robot_schedule(
        request: schemas.RobotScheduleUpdateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Обновление расписания робота в robot_schedules."""
    try:
        robot = await service.robot_service.update_robot_schedule(
            db=db,
            robot_id=request.robotId,
            user_id=current_user.id,
            poll_interval_hours=request.poll_interval_hours,
            trading_hours_start=request.trading_hours_start,
            trading_hours_end=request.trading_hours_end,
            allowed_weekdays=request.allowed_weekdays,
        )
        return schemas.RobotInDB.model_validate(robot)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении расписания: {str(e)}"
        )


@router.get("/trading-defaults", response_model=schemas.RobotTradingDefaultsResponse)
async def get_robot_trading_defaults():
    """Доли комиссии и НДФЛ из settings.robots (и .env ROBOTS__*)."""
    from app.core.config import settings
    return schemas.RobotTradingDefaultsResponse(
        broker_commission_rate=float(settings.robots.broker_commission_rate),
        ndfl_rate=float(settings.robots.ndfl_rate),
    )


@router.post("/history-backtest", response_model=schemas.RobotHistoryBacktestResponse)
async def run_robot_history_backtest(
        request: schemas.RobotHistoryBacktestRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Исторический бэктест стратегии робота на свечах T-Invest."""
    return await robot_backtest_usecase.execute(db, current_user.id, request)


@router.post("/live/snapshot", response_model=schemas.RobotLiveSnapshotResponse)
async def get_robot_live_snapshot(
        request: schemas.RobotLiveSnapshotRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await robot_live_snapshot_usecase.execute(db, current_user.id, request.robotId)
    return schemas.RobotLiveSnapshotResponse(**data)


@router.post("/history-backtest/list", response_model=schemas.RobotBacktestHistoryResponse)
async def list_robot_backtest_history(
        request: schemas.RobotBacktestHistoryRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.get_backtest_history(
        db=db,
        robot_id=request.robotId,
        user_id=current_user.id,
        limit=request.limit,
    )
    return schemas.RobotBacktestHistoryResponse(**data)


@router.post("/history-backtest/run", response_model=schemas.RobotBacktestRunDetailsResponse)
async def get_robot_backtest_run_details(
        request: schemas.RobotBacktestRunRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.get_backtest_run_details(
        db=db,
        run_id=request.runId,
        user_id=current_user.id,
    )
    return schemas.RobotBacktestRunDetailsResponse(**data)


@router.post("/history-backtest/compare", response_model=schemas.RobotBacktestCompareResponse)
async def compare_robot_backtest_runs(
        request: schemas.RobotBacktestCompareRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.compare_backtest_runs(
        db=db,
        base_run_id=request.baseRunId,
        compare_run_id=request.compareRunId,
        user_id=current_user.id,
        name=request.name,
    )
    return schemas.RobotBacktestCompareResponse(**data)


@router.post("/history-backtest/compare/list", response_model=schemas.RobotBacktestCompareListResponse)
async def list_robot_backtest_comparisons(
        request: schemas.RobotBacktestCompareListRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.list_backtest_comparisons(
        db=db,
        user_id=current_user.id,
        limit=request.limit,
        offset=request.offset,
    )
    return schemas.RobotBacktestCompareListResponse(**data)


@router.post("/history-backtest/compare/id", response_model=schemas.RobotBacktestCompareResponse)
async def get_robot_backtest_comparison(
        request: schemas.RobotBacktestCompareIdRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.get_backtest_comparison(
        db=db,
        comparison_id=request.comparisonId,
        user_id=current_user.id,
    )
    return schemas.RobotBacktestCompareResponse(**data)


@router.post("/history-backtest/compare", response_model=schemas.RobotBacktestCompareResponse)
async def compare_robot_backtest_runs(
        request: schemas.RobotBacktestCompareRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = await service.robot_service.compare_backtest_runs(
        db=db,
        base_run_id=request.baseRunId,
        compare_run_id=request.compareRunId,
        user_id=current_user.id,
        name=request.name,
    )
    return schemas.RobotBacktestCompareResponse(**data)


@router.post("/instruments/auto-select")
async def auto_select_instruments(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Автоподбор топ-20 инструментов по ликвидности."""
    from app.modules.robots.trading.instrument_selector import InstrumentSelector
    from app.modules.tinvest.token_service import token_service

    token_data = await token_service.get_active_token(db, current_user.id)
    if not token_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нет активного токена")

    selector = InstrumentSelector(token_data["token"])
    try:
        instruments = await selector.select_instruments()
        return {"items": instruments, "total": len(instruments)}
    finally:
        await selector.close()


