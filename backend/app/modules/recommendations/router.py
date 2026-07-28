from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User

from .schemas import (
    OptimizationBatchCancelResponse,
    OptimizationBatchStartedResponse,
    OptimizationBatchStatusResponse,
    OptimizationGoal,
    OptimizationMode,
    OptimizationPlanRequest,
    OptimizationPlanResponse,
    OptimizationRankResponse,
    OptimizationRunRequest,
    OptimizationSessionFailuresResponse,
    RobotRecommendationsResponse,
    StrategyTipsResponse,
)
from .service import recommendations_service

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/robots/{robot_id}", response_model=RobotRecommendationsResponse)
async def get_robot_recommendations(
    robot_id: int,
    backtest_limit: int = Query(15, ge=1, le=50, description="Сколько успешных бэктестов анализировать"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Рекомендации по стратегии и настройкам робота:
    сравнение лучшего бэктеста с текущим конфигом, лайв-метрики, риск-события.
    """
    result = await recommendations_service.get_robot_recommendations(
        db,
        robot_id=robot_id,
        user_id=current_user.id,
        schema=settings.DB_SCHEMA,
        backtest_limit=backtest_limit,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Торговый робот не найден")
    return result


@router.get("/strategies/{strategy_name}", response_model=StrategyTipsResponse)
def get_strategy_tips(
    strategy_name: str,
    current_user: User = Depends(get_current_user),
):
    """Общие подсказки по выбранной стратегии (без привязки к роботу)."""
    result = recommendations_service.get_strategy_tips(strategy_name.strip().lower())
    if not result:
        raise HTTPException(status_code=404, detail="Стратегия не найдена")
    return result


@router.get(
    "/robots/{robot_id}/optimize/rank",
    response_model=OptimizationRankResponse,
)
async def rank_robot_backtests(
    robot_id: int,
    goal: OptimizationGoal = Query(
        OptimizationGoal.BALANCED,
        description="Цель скоринга: balanced | max_return | min_drawdown | max_sharpe",
    ),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ранжирование успешных бэктестов робота по composite score."""
    result = await recommendations_service.rank_backtest_runs(
        db,
        robot_id=robot_id,
        user_id=current_user.id,
        schema=settings.DB_SCHEMA,
        goal=goal,
        limit=limit,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Торговый робот не найден")
    return result


@router.get(
    "/optimize/session-failures",
    response_model=OptimizationSessionFailuresResponse,
)
async def session_optimization_failures(
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Неуспешные прогоны тестирования без robot_id (crypto/MOEX из формы)."""
    return await recommendations_service.session_optimization_failures(
        db,
        user_id=current_user.id,
        schema=settings.DB_SCHEMA,
        limit=limit,
    )


@router.post(
    "/robots/{robot_id}/optimize/plan",
    response_model=OptimizationPlanResponse,
)
async def plan_robot_optimization(
    robot_id: int,
    body: OptimizationPlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сетка кандидатов конфигурации для оптимизации."""
    result = await recommendations_service.plan_optimization(
        db,
        robot_id=robot_id,
        user_id=current_user.id,
        goal=body.goal,
        mode=body.mode,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Торговый робот не найден")
    return result


@router.post(
    "/robots/{robot_id}/optimize/run",
    response_model=OptimizationBatchStartedResponse,
    status_code=202,
)
async def run_robot_optimization_batch(
    robot_id: int,
    body: OptimizationRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Асинхронный массовый прогон сетки параметров (N бэктестов в очереди heavy)."""
    result = await recommendations_service.run_optimization_batch(
        db,
        robot_id=robot_id,
        user_id=current_user.id,
        schema=settings.DB_SCHEMA,
        body=body,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Торговый робот не найден")
    return result


@router.get(
    "/robots/{robot_id}/optimize/batches/active",
    response_model=OptimizationBatchStatusResponse | None,
)
def get_active_optimization_batch(
    robot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return recommendations_service.get_active_optimization_batch(
        db,
        robot_id=robot_id,
        user_id=current_user.id,
        schema=settings.DB_SCHEMA,
    )


@router.get(
    "/robots/{robot_id}/optimize/batches/{batch_id}",
    response_model=OptimizationBatchStatusResponse,
)
def get_optimization_batch_status_endpoint(
    robot_id: int,
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = recommendations_service.get_optimization_batch(
        db,
        batch_id=batch_id,
        user_id=current_user.id,
        schema=settings.DB_SCHEMA,
    )
    if not result or result.robot_id != robot_id:
        raise HTTPException(status_code=404, detail="Пакет оптимизации не найден")
    return result


@router.post(
    "/robots/{robot_id}/optimize/batches/{batch_id}/cancel",
    response_model=OptimizationBatchCancelResponse,
)
async def cancel_optimization_batch_endpoint(
    robot_id: int,
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = recommendations_service.get_optimization_batch(
        db,
        batch_id=batch_id,
        user_id=current_user.id,
        schema=settings.DB_SCHEMA,
    )
    if not existing or existing.robot_id != robot_id:
        raise HTTPException(status_code=404, detail="Пакет оптимизации не найден")
    result = await recommendations_service.cancel_optimization_batch(
        db,
        batch_id=batch_id,
        user_id=current_user.id,
        schema=settings.DB_SCHEMA,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Пакет оптимизации не найден")
    return result
