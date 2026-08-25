"""Bootstrap sync-only cycle before trading."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.engine.session import TradingSessionV2
from app.modules.robots_v2.engine.types import SessionState
from app.modules.robots_v2.risk.engine import RiskEngine


def _minimal_config() -> dict:
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


def test_bootstrap_sync_paper_unlocks_without_trading():
    session = TradingSessionV2(
        robot_id=1,
        user_id=1,
        token_id=1,
        config=_minimal_config(),
        virtual_capital=100_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(_minimal_config())
    session.universe = ["SBER"]
    session.ledger = PaperLedger(cash=100_000, commission_rate=0.0005)
    session.risk = RiskEngine(session._parsed.risk)
    session.execution = MagicMock()
    session.execution.account_id = None
    session.execution.sync_orders_from_broker = AsyncMock(return_value=[])
    session._persist_skip_cycle = AsyncMock()
    session._set_stage = AsyncMock()
    session._ensure_instrument_map = AsyncMock()
    session._audit_extra_tickers = AsyncMock(return_value=set())

    async def _run() -> bool:
        with patch(
            "app.modules.robots_v2.engine.session.fetch_prices_for_session",
            new=AsyncMock(return_value={"SBER": 250.0}),
        ), patch(
            "app.modules.robots_v2.engine.session.SessionLocal",
            return_value=MagicMock(**{"close": MagicMock()}),
        ):
            return await session._bootstrap_sync_once()

    ok = asyncio.run(_run())
    assert ok is True
    assert session.last_prices.get("SBER") == 250.0
    assert session.cycle_number == 1
    assert session._last_triggered_by == "bootstrap_sync"
    session.execution.sync_orders_from_broker.assert_not_called()


def test_poll_cycle_blocked_until_bootstrap_ready():
    session = TradingSessionV2(
        robot_id=1,
        user_id=1,
        token_id=1,
        config=_minimal_config(),
        virtual_capital=100_000,
    )
    session.state = SessionState.RUNNING
    session._parsed = TradingRobotConfigV4.model_validate(_minimal_config())
    session.ledger = PaperLedger(cash=100_000, commission_rate=0.0005)
    session.risk = RiskEngine(session._parsed.risk)
    session.execution = MagicMock()
    session._bootstrap_ready = False

    asyncio.run(session._poll_cycle(triggered_by="poll"))
    assert session.cycle_number == 0
    assert session._last_triggered_by is None
