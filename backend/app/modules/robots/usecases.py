from __future__ import annotations

from typing import Dict, Any

from sqlalchemy.orm import Session

#///EPIC Backtesting.ITEM RobotsAPI.TOPIC UseCase Delegation [1]
#/// Лёгкий слой usecase: делегирует backtest/live snapshot в robot_service,
#/// удерживая единый вход для роутера и последующего расширения orchestration.
from . import schemas
from .service import robot_service


class RobotBacktestUseCase:
    async def execute(
        self,
        db: Session,
        user_id: int,
        request: schemas.RobotHistoryBacktestRequest,
    ) -> Dict[str, Any]:
        return await robot_service.run_robot_history_backtest(db, user_id, request)


class RobotLiveSnapshotUseCase:
    async def execute(
        self,
        db: Session,
        user_id: int,
        robot_id: int,
        *,
        mode: str = "full",
    ) -> Dict[str, Any]:
        return await robot_service.get_live_snapshot(db, robot_id, user_id, mode=mode)


robot_backtest_usecase = RobotBacktestUseCase()
robot_live_snapshot_usecase = RobotLiveSnapshotUseCase()
