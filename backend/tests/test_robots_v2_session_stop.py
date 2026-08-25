"""Stop must not hang while bootstrap is blocked on universe/DMS."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.session import TradingSessionV2
from app.modules.robots_v2.engine.types import SessionState


def _cfg() -> dict:
    return {
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "mode": "paper",
            "instrumentType": "stock",
            "schedule": {
                "weekdays": [True, True, True, True, True, False, False],
                "timeFrom": "10:00",
                "timeTo": "18:40",
                "pollInterval": "5m",
            },
        },
        "universe": {"mode": "fixed", "fixedList": ["SBER"], "maxAssets": 5},
        "strategy": {
            "archetype": "momentum",
            "timeframe": "1h",
            "params": {"maPeriod": 50, "volumeMultiplier": 2.0, "breakoutLookback": 20},
        },
        "risk": {
            "capital": 100_000,
            "maxPositionSharePct": 10,
            "stopLossPct": 2,
            "takeProfitPct": 4,
            "maxDailyLoss": 5000,
            "maxConcurrentPositions": 3,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
        },
    }


def test_stop_aborts_hung_universe_resolve():
    cfg = _cfg()
    session = TradingSessionV2(
        robot_id=99, user_id=1, token_id=1, config=cfg, virtual_capital=100_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(cfg)

    async def hung() -> tuple[list[str], dict[str, str]]:
        await asyncio.sleep(30)
        return ["SBER"], {"SBER": "FIGI"}

    async def _run() -> None:
        result = await session._await_or_stop(hung(), what="universe_resolve")
        assert result is None
        session.state = SessionState.TERMINATED

    async def scenario() -> None:
        session.state = SessionState.BOOTSTRAP
        session._task = asyncio.create_task(_run())
        await asyncio.sleep(0.05)
        await session.stop()
        assert session._stop_event.is_set()
        assert session._task.done()

    asyncio.run(scenario())


def test_stop_joins_finished_task():
    cfg = _cfg()
    session = TradingSessionV2(
        robot_id=98, user_id=1, token_id=1, config=cfg, virtual_capital=100_000,
    )

    async def scenario() -> None:
        async def quick() -> None:
            session.state = SessionState.TERMINATED

        session._task = asyncio.create_task(quick())
        await session.stop()
        assert session._task.done()
        assert session.state == SessionState.TERMINATED

    asyncio.run(scenario())
