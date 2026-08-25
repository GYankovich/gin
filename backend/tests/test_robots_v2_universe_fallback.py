"""Fallback universe when screener returns 0 symbols."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.session import TradingSessionV2


def _screener_config() -> dict:
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
        "universe": {
            "mode": "screener",
            "screener": {"preset": "volatile"},
            "maxAssets": 20,
        },
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
        "metadata": {
            "universeSnapshot": [{"ticker": "PLZL"}, {"ticker": "BANEP"}],
        },
    }


def test_fallback_universe_from_audit_and_snapshot():
    session = TradingSessionV2(
        robot_id=1,
        user_id=1,
        token_id=1,
        config=_screener_config(),
        virtual_capital=100_000,
    )
    session._parsed = TradingRobotConfigV4.model_validate(_screener_config())

    mock_db = MagicMock()
    with patch(
        "app.modules.robots_v2.engine.session.SessionLocal",
        return_value=mock_db,
    ), patch(
        "app.modules.robots_v2.engine.broker_positions.open_tickers_from_audit_fills",
        return_value={"X5": None, "ROSN": None, "SMLT": None},
    ):
        tickers = asyncio.run(session._fallback_universe_tickers())

    assert tickers == ["BANEP", "PLZL", "ROSN", "SMLT", "X5"]
