"""
Legacy RobotScheduler wrapper — trading scheduler removed; schedule policy kept for stages/tests.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from app.modules.robots.scheduling.schedule_policy import should_start_trading_session


class RobotScheduler:
    def should_run(
        self,
        robot: Dict[str, Any],
        *,
        now: Optional[datetime] = None,
    ) -> bool:
        return should_start_trading_session(robot, now=now)

    async def tick(self) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def force_run(self, robot_id: int) -> Dict[str, Any]:
        return {"status": "disabled", "robot_id": robot_id, "reason": "legacy trading scheduler removed"}


_default_robot_scheduler: Optional[RobotScheduler] = None


def get_robot_scheduler() -> RobotScheduler:
    global _default_robot_scheduler
    if _default_robot_scheduler is None:
        _default_robot_scheduler = RobotScheduler()
    return _default_robot_scheduler


__all__ = ["RobotScheduler", "get_robot_scheduler", "should_start_trading_session"]
