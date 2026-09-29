"""Failure-mode guards for v2 backtest persist / empty candles."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.robots_v2.backtest.persist import update_db_run, update_db_run_required


def test_update_db_run_returns_false_on_failure():
    db = MagicMock()
    db.execute.side_effect = RuntimeError("db down")
    assert update_db_run(db, 1, progress_percent=10) is False
    db.rollback.assert_called()


def test_update_db_run_required_raises_on_critical_failure():
    db = MagicMock()
    db.execute.side_effect = RuntimeError("db down")
    with pytest.raises(RuntimeError, match="failed to persist"):
        update_db_run_required(db, 7, status="CANCELLED", cancel_requested=True)


def test_update_db_run_required_ok_on_progress_only_failure():
    """Non-critical fields may soft-fail without raising."""
    db = MagicMock()
    db.execute.side_effect = RuntimeError("db down")
    # progress_percent alone is not critical — helper still raises only for critical set
    # calling with only progress should not raise even if write fails
    update_db_run_required(db, 7, progress_percent=50.0)


def test_host_empty_timeline_reports_zero_bars():
    from app.modules.robots_v2.backtest.host import BacktestHost
    from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4

    cfg = TradingRobotConfigV4.model_validate({
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "instrumentType": "stock",
            "mode": "paper",
            "schedule": {
                "weekdays": [True, True, True, True, True, False, False],
                "timeFrom": "10:00",
                "timeTo": "18:40",
                "pollInterval": "5m",
            },
        },
        "strategy": {
            "archetype": "momentum",
            "timeframe": "1h",
            "params": {"maPeriod": 20, "volumeMultiplier": 2.0, "breakoutLookback": 10},
        },
        "universe": {"mode": "fixed", "fixedList": ["SBER"], "maxAssets": 5},
        "risk": {
            "capital": 100_000,
            "maxPositionSharePct": 10,
            "stopLossPct": 2,
            "takeProfitPct": 4,
            "maxDailyLoss": 5000,
            "maxConcurrentPositions": 1,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
        },
    })
    host = BacktestHost()
    result = host.run_sync(
        config=cfg,
        universe=["SBER"],
        candles_by_ticker={"SBER": []},
        initial_capital=100_000,
        session_id=1,
        trade_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    assert result.history_stats.get("bars") == 0
    assert result.stages and "No candle data" in result.stages[0]
