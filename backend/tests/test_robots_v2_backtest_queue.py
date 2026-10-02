"""ARCH-05 phase A: v2 backtest enqueue + worker handler wiring."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.core.background_jobs.handlers import JOB_HANDLERS
from app.modules.robots_v2.backtest.quotas import assert_can_enqueue_backtest
from app.modules.robots_v2.backtest.schemas import RobotV2BacktestRequest
from app.modules.robots_v2.backtest.service import BacktestService
from app.modules.robots_v2.backtest.worker_handler import JOB_TYPE_BACKTEST_RUN


def _sample_config_dict() -> dict:
    return {
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "instrumentType": "stock",
            "mode": "paper",
            "advancedMode": False,
            "schedule": {
                "weekdays": [True, True, True, True, True, True, True],
                "timeFrom": "00:00",
                "timeTo": "23:59",
                "pollInterval": "5m",
            },
        },
        "strategy": {
            "archetype": "momentum",
            "timeframe": "1h",
            "params": {"maPeriod": 20, "volumeMultiplier": 1.5, "breakoutLookback": 5},
        },
        "universe": {
            "mode": "fixed",
            "fixedList": ["SBER"],
            "excluded": [],
            "maxAssets": 5,
            "exitOnDrop": False,
        },
        "risk": {
            "capital": 100_000,
            "maxPositionSharePct": 50,
            "stopLossPct": 5,
            "takeProfitPct": 10,
            "maxDailyLoss": 50_000,
            "maxDrawdownPct": 50,
            "maxConcurrentPositions": 3,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
            "slippagePct": 0.5,
            "stopMode": "soft",
        },
    }


def test_backtest_run_handler_registered():
    assert JOB_TYPE_BACKTEST_RUN in JOB_HANDLERS
    assert JOB_HANDLERS[JOB_TYPE_BACKTEST_RUN] is not None


def test_history_backtest_job_type_removed():
    import asyncio

    from app.core.background_jobs.handlers import execute_job_handler

    assert "history_backtest" not in JOB_HANDLERS

    async def _run():
        with pytest.raises(RuntimeError, match="Unknown background job type"):
            await execute_job_handler("history_backtest", {"run_id": 123})

    asyncio.run(_run())


def test_start_enqueues_without_create_task():
    svc = BacktestService()
    db = MagicMock()
    request = RobotV2BacktestRequest(
        config=_sample_config_dict(),
        from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        to_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        initial_capital=100_000,
        robot_id=13,
        async_execution=False,
    )

    async def _run():
        with (
            patch("app.modules.robots_v2.backtest.service.assert_can_enqueue_backtest"),
            patch(
                "app.modules.robots_v2.backtest.service.create_db_run",
                return_value=501,
            ) as create_mock,
            patch(
                "app.modules.robots_v2.backtest.service.enqueue_background_job",
                return_value="job-uuid",
            ) as enqueue_mock,
            patch.object(svc, "_execute") as execute_mock,
            patch("asyncio.create_task") as create_task_mock,
        ):
            rec, enqueued = await svc.start(db, user_id=7, request=request)
            return rec, enqueued, create_mock, enqueue_mock, execute_mock, create_task_mock

    rec, enqueued, create_mock, enqueue_mock, execute_mock, create_task_mock = asyncio.run(_run())

    assert enqueued is True
    assert rec.run_id == 501
    assert rec.status == "QUEUED"
    create_mock.assert_called_once()
    enqueue_mock.assert_called_once()
    kwargs = enqueue_mock.call_args.kwargs
    assert kwargs["job_type"] == JOB_TYPE_BACKTEST_RUN
    assert kwargs["lane"] == "heavy"
    assert kwargs["payload"]["run_id"] == 501
    assert kwargs["payload"]["user_id"] == 7
    assert kwargs["idempotency_key"] == "backtest_run:501"
    execute_mock.assert_not_called()
    create_task_mock.assert_not_called()
    db.commit.assert_called()


def test_start_requires_db_row():
    svc = BacktestService()
    db = MagicMock()
    request = RobotV2BacktestRequest(
        config=_sample_config_dict(),
        from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        to_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )

    async def _run():
        with (
            patch("app.modules.robots_v2.backtest.service.assert_can_enqueue_backtest"),
            patch("app.modules.robots_v2.backtest.service.create_db_run", return_value=None),
        ):
            await svc.start(db, user_id=1, request=request)

    with pytest.raises(HTTPException) as ei:
        asyncio.run(_run())
    assert ei.value.status_code == 503


def test_quota_span_too_long():
    db = MagicMock()
    with patch("app.modules.robots_v2.backtest.quotas.settings") as settings_mock:
        settings_mock.COMPUTE_MAX_SPAN_DAYS = 30
        settings_mock.COMPUTE_MAX_USER_RUNNING = 1
        settings_mock.COMPUTE_MAX_USER_QUEUED = 10
        with pytest.raises(HTTPException) as ei:
            assert_can_enqueue_backtest(
                db,
                user_id=1,
                from_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                to_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
            )
    assert ei.value.status_code == 400
    assert ei.value.detail["code"] == "span_too_long"


def test_quota_user_running():
    db = MagicMock()
    with (
        patch("app.modules.robots_v2.backtest.quotas.settings") as settings_mock,
        patch(
            "app.modules.robots_v2.backtest.quotas.count_v2_runs_by_status",
            side_effect=[1, 0],
        ),
    ):
        settings_mock.COMPUTE_MAX_SPAN_DAYS = 366
        settings_mock.COMPUTE_MAX_USER_RUNNING = 1
        settings_mock.COMPUTE_MAX_USER_QUEUED = 10
        with pytest.raises(HTTPException) as ei:
            assert_can_enqueue_backtest(
                db,
                user_id=1,
                from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                to_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            )
    assert ei.value.status_code == 429
    assert ei.value.detail["code"] == "quota_user_running"


def test_handle_backtest_run_calls_execute():
    from app.modules.robots_v2.backtest import worker_handler as wh
    from app.modules.robots_v2.backtest.service import backtest_service

    row = {
        "run_id": 77,
        "user_id": 3,
        "robot_id": 13,
        "status": "QUEUED",
        "cancel_requested": False,
        "requested_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "requested_to": datetime(2026, 1, 10, tzinfo=timezone.utc),
        "started_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "initial_capital": 100_000,
        "config_snapshot": _sample_config_dict(),
    }
    called: dict = {}

    async def _exec(user_id, run_id, config, request):
        called["user_id"] = user_id
        called["run_id"] = run_id
        called["archetype"] = config.strategy.archetype
        called["token_id"] = request.token_id

    async def _run():
        with (
            patch.object(wh, "get_db_context") as ctx_mock,
            patch.object(wh, "fetch_db_run_by_id", return_value=row),
            patch.object(backtest_service, "execute_run", side_effect=_exec),
        ):
            ctx_mock.return_value.__enter__ = MagicMock(return_value=MagicMock())
            ctx_mock.return_value.__exit__ = MagicMock(return_value=False)
            await wh.handle_backtest_run({"run_id": 77, "user_id": 3, "token_id": 9})

    asyncio.run(_run())

    assert called == {
        "user_id": 3,
        "run_id": 77,
        "archetype": "momentum",
        "token_id": 9,
    }
