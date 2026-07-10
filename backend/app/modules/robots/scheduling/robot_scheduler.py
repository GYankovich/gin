"""
RobotScheduler — единый tick для торговых роботов type=2 (BRD-ARCH-04 §4.5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING

from app.modules.robots.scheduling.schedule_policy import should_start_trading_session

if TYPE_CHECKING:
    from app.modules.robots.trading.scheduler import TradingScheduler


class RobotScheduler:
    def __init__(self, inner: Optional["TradingScheduler"] = None):
        if inner is None:
            from app.modules.robots.trading.scheduler import trading_scheduler

            inner = trading_scheduler
        self._inner = inner

    def should_run(
        self,
        robot: Dict[str, Any],
        *,
        now: Optional[datetime] = None,
    ) -> bool:
        return should_start_trading_session(robot, now=now)

    async def tick(self) -> None:
        await self._inner._run_cycle()

    async def start(self) -> None:
        await self._inner.start()

    async def stop(self) -> None:
        await self._inner.stop()

    async def force_run(self, robot_id: int) -> Dict[str, Any]:
        return await self._inner.force_run(robot_id)


_default_robot_scheduler: Optional[RobotScheduler] = None


def get_robot_scheduler() -> RobotScheduler:
    global _default_robot_scheduler
    if _default_robot_scheduler is None:
        _default_robot_scheduler = RobotScheduler()
    return _default_robot_scheduler


__all__ = ["RobotScheduler", "get_robot_scheduler", "should_start_trading_session"]
