"""ARCH-05 A.2: optimization batch enqueues v2 backtest_run jobs."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.recommendations.optimization_engine import (
    generate_grid_configs,
    resolve_strategy_key,
)
from app.modules.recommendations.optimization_runner import _enqueue_variant_backtest
from app.modules.robots_v2.backtest.quotas import assert_can_start_optimization_batch
from app.modules.robots_v2.backtest.store import BacktestRunRecord


def _v4_momentum_config() -> dict:
    return {
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "instrumentType": "stock",
            "mode": "paper",
            "advancedMode": False,
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
            "params": {
                "maPeriod": 40,
                "volumeMultiplier": 2.0,
                "breakoutLookback": 20,
            },
        },
        "universe": {
            "mode": "fixed",
            "fixedList": ["SBER", "GAZP"],
            "excluded": [],
            "maxAssets": 10,
            "exitOnDrop": False,
        },
        "risk": {
            "capital": 100_000,
            "maxPositionSharePct": 25,
            "stopLossPct": 3,
            "takeProfitPct": 6,
            "maxDailyLoss": 5000,
            "maxDrawdownPct": 50,
            "maxConcurrentPositions": 3,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
            "slippagePct": 0.5,
            "stopMode": "soft",
        },
    }


def test_resolve_strategy_key_v4():
    assert resolve_strategy_key(_v4_momentum_config()) == "momentum"


def test_generate_grid_v4_momentum_produces_valid_variants():
    variants = generate_grid_configs(_v4_momentum_config(), mode="speed")
    assert len(variants) >= 1
    assert all(v.get("configVersion") == 4 for v in variants)
    assert all(v["strategy"]["archetype"] == "momentum" for v in variants)
    # stop < take always
    for v in variants:
        assert v["risk"]["stopLossPct"] < v["risk"]["takeProfitPct"]


def test_generate_grid_scalper_empty():
    cfg = _v4_momentum_config()
    cfg["strategy"]["archetype"] = "scalper"
    cfg["strategy"]["params"] = {
        "deltaThresholdPct": 5,
        "requiresWebSocket": True,
    }
    assert generate_grid_configs(cfg, mode="speed") == []


def test_batch_too_large():
    with pytest.raises(HTTPException) as ei:
        assert_can_start_optimization_batch(
            from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            to_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
            variants_count=999,
        )
    assert ei.value.status_code == 400
    assert ei.value.detail["code"] == "batch_too_large"


def test_enqueue_variant_uses_backtest_service_batch_priority():
    db = MagicMock()
    rec = BacktestRunRecord(
        run_id=901,
        user_id=1,
        robot_id=13,
        status="QUEUED",
        requested_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        requested_to=datetime(2026, 1, 10, tzinfo=timezone.utc),
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        initial_capital=100_000,
    )

    async def _run():
        with patch(
            "app.modules.robots_v2.backtest.service.backtest_service"
        ) as svc:
            svc.start = AsyncMock(return_value=(rec, True))
            rid = await _enqueue_variant_backtest(
                db,
                user_id=1,
                robot_id=13,
                variant_config=_v4_momentum_config(),
                requested_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                requested_to=datetime(2026, 1, 10, tzinfo=timezone.utc),
                initial_capital=100_000,
                token_id=5,
            )
            return rid, svc.start

    rid, start_mock = asyncio.run(_run())
    assert rid == 901
    start_mock.assert_awaited_once()
    assert start_mock.await_args.kwargs.get("priority") == "batch"
