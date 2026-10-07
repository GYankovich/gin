"""SPEC-05 P0: Backtest Lab orphan runs (soft bind / nullify / lab list)."""

from __future__ import annotations

import asyncio
import json
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

from app.modules.robots_v2.backtest.persist import (
    _bound_robot_id_from_run,
    _config_label_from_snapshot,
    _row_to_dict,
    _snapshot_for_run,
    compare_runs,
    create_db_run,
    list_db_runs,
    nullify_robot_soft_bind,
    trading_config_from_snapshot,
)
from app.modules.robots_v2.backtest.schemas import RobotV2BacktestSaveAsRobotRequest
from app.modules.robots_v2.backtest.schemas import (
    RobotV2BacktestListItem,
    RobotV2BacktestRequest,
)
from app.modules.robots_v2.backtest.service import BacktestService
from app.modules.robots_v2.schemas import RobotV2Response
from app.modules.robots_v2.service import RobotsV2Service


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


def test_trading_config_from_snapshot_strips_lab_meta():
    cfg = trading_config_from_snapshot(
        {"strategy": {"archetype": "momentum"}, "engine_version": "v2", "v2RobotId": 12, "core": {"mode": "paper"}},
    )
    assert cfg["strategy"]["archetype"] == "momentum"
    assert "engine_version" not in cfg
    assert "v2RobotId" not in cfg


def test_bound_robot_id_from_run_prefers_robot_id_column():
    assert _bound_robot_id_from_run({"robot_id": 7, "config_snapshot": {"v2RobotId": 9}}) == 7
    assert _bound_robot_id_from_run({"robot_id": None, "config_snapshot": {"v2RobotId": 9}}) == 9
    assert _bound_robot_id_from_run({"robot_id": None, "config_snapshot": {}}) is None


def test_snapshot_for_orphan_omits_v2_robot_id():
    snap = _snapshot_for_run({"strategy": {"archetype": "momentum"}, "v2RobotId": 99}, None)
    assert snap["engine_version"] == "v2"
    assert "v2RobotId" not in snap


def test_snapshot_for_bound_sets_v2_robot_id():
    snap = _snapshot_for_run({"strategy": {"archetype": "grid"}}, 42)
    assert snap["v2RobotId"] == 42
    assert snap["engine_version"] == "v2"


def test_create_db_run_orphan_persists_null_robot_id():
    db = MagicMock()
    db.execute.return_value.scalar.return_value = 901

    run_id = create_db_run(
        db,
        user_id=7,
        robot_id=None,
        requested_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        requested_to=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=1_000_000,
        config_snapshot=_sample_config_dict(),
    )

    assert run_id == 901
    assert db.execute.call_count == 1
    params = db.execute.call_args.args[1]
    assert params["robot_id"] is None
    assert params["user_id"] == 7
    snap = json.loads(params["config_snapshot"])
    assert snap["engine_version"] == "v2"
    assert "v2RobotId" not in snap
    db.commit.assert_called()


def test_create_db_run_rejects_fake_robot_id_zero():
    db = MagicMock()
    db.execute.return_value.scalar.return_value = 902

    run_id = create_db_run(
        db,
        user_id=7,
        robot_id=0,
        requested_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        requested_to=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=100_000,
        config_snapshot=_sample_config_dict(),
    )

    assert run_id == 902
    params = db.execute.call_args.args[1]
    assert params["robot_id"] is None
    snap = json.loads(params["config_snapshot"])
    assert "v2RobotId" not in snap


def test_create_db_run_bound_sets_v2_robot_id():
    db = MagicMock()
    db.execute.return_value.scalar.return_value = 903

    create_db_run(
        db,
        user_id=7,
        robot_id=13,
        requested_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        requested_to=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=100_000,
        config_snapshot=_sample_config_dict(),
    )

    params = db.execute.call_args.args[1]
    assert params["robot_id"] == 13
    snap = json.loads(params["config_snapshot"])
    assert snap["v2RobotId"] == 13


def test_list_db_runs_lab_default_has_no_robot_filter():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = []

    list_db_runs(db, user_id=7, robot_id=None, limit=30)

    sql = str(db.execute.call_args.args[0])
    params = db.execute.call_args.args[1]
    assert "user_id = :uid" in sql
    assert "robot_id = :robot_id" not in sql
    assert "robot_id" not in params
    assert params["uid"] == 7


def test_list_db_runs_robot_filter_keeps_or_v2_robot_id():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = []

    list_db_runs(db, user_id=7, robot_id=13, limit=20)

    sql = str(db.execute.call_args.args[0])
    params = db.execute.call_args.args[1]
    assert "robot_id = :robot_id" in sql
    assert "v2RobotId" in sql
    assert params["robot_id"] == 13


def test_row_to_dict_bound_and_config_label():
    orphan = _row_to_dict(
        {
            "id": 1,
            "robot_id": None,
            "status": "SUCCESS",
            "requested_from": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "requested_to": datetime(2024, 2, 1, tzinfo=timezone.utc),
            "started_at": datetime(2024, 2, 2, tzinfo=timezone.utc),
            "finished_at": None,
            "initial_capital": 100_000,
            "progress_percent": 100,
            "run_phase": "done",
            "cancel_requested": False,
            "error_message": None,
            "config_snapshot": {"strategy": {"archetype": "momentum"}, "engine_version": "v2"},
            "metrics_summary": {},
        }
    )
    assert orphan["bound"] is False
    assert orphan["robot_id"] is None
    assert orphan["config_label"] == "momentum"

    bound = _row_to_dict(
        {
            "id": 2,
            "robot_id": 55,
            "status": "SUCCESS",
            "requested_from": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "requested_to": datetime(2024, 2, 1, tzinfo=timezone.utc),
            "started_at": datetime(2024, 2, 2, tzinfo=timezone.utc),
            "finished_at": None,
            "initial_capital": 100_000,
            "progress_percent": 100,
            "run_phase": "done",
            "cancel_requested": False,
            "error_message": None,
            "config_snapshot": {"strategy": {"archetype": "grid"}, "v2RobotId": 55},
            "metrics_summary": {},
        }
    )
    assert bound["bound"] is True
    assert bound["robot_id"] == 55
    item = RobotV2BacktestListItem.model_validate(bound)
    assert item.bound is True
    assert item.config_label == "grid"


def test_config_label_helper():
    assert _config_label_from_snapshot({"strategy": {"archetype": "reversion"}}) == "reversion"
    assert _config_label_from_snapshot({"name": "My bot"}) == "My bot"
    assert _config_label_from_snapshot({}) is None
    assert _config_label_from_snapshot(None) is None


def test_nullify_robot_soft_bind_sql():
    db = MagicMock()
    db.execute.return_value.rowcount = 3

    n = nullify_robot_soft_bind(db, robot_id=42)

    assert n == 3
    sql = str(db.execute.call_args.args[0])
    params = db.execute.call_args.args[1]
    assert "robot_id = NULL" in sql
    assert "v2RobotId" in sql
    assert params["robot_id"] == 42


def test_compare_orphan_to_orphan():
    base = {
        "run_id": 10,
        "robot_id": None,
        "status": "SUCCESS",
        "requested_from": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "requested_to": datetime(2024, 2, 1, tzinfo=timezone.utc),
        "initial_capital": 100_000,
        "trades_total": 2,
        "config_snapshot": {"strategy": {"archetype": "momentum"}, "engine_version": "v2"},
        "result_payload": {
            "total_return_percent": 1.5,
            "max_drawdown_percent": -2.0,
            "final_equity": 101_500,
            "sharpe_ratio": 0.8,
        },
    }
    other = {
        "run_id": 11,
        "robot_id": None,
        "status": "SUCCESS",
        "requested_from": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "requested_to": datetime(2024, 3, 1, tzinfo=timezone.utc),
        "initial_capital": 100_000,
        "trades_total": 4,
        "config_snapshot": {"strategy": {"archetype": "grid"}, "engine_version": "v2"},
        "result_payload": {
            "total_return_percent": 3.0,
            "max_drawdown_percent": -1.0,
            "final_equity": 103_000,
            "sharpe_ratio": 1.1,
        },
    }
    out = compare_runs(base, other)
    assert out["base_run_id"] == 10
    assert out["compare_run_id"] == 11
    assert out["metrics_diff"]["total_return_percent"] == pytest.approx(1.5)
    assert "strategy.archetype" in out["config_diff"]


def test_start_orphan_without_robot_id():
    svc = BacktestService()
    db = MagicMock()
    request = RobotV2BacktestRequest(
        config=_sample_config_dict(),
        from_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        to_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        initial_capital=1_000_000,
    )
    assert request.robot_id is None

    async def _run():
        with (
            patch("app.modules.robots_v2.backtest.service.assert_can_enqueue_backtest"),
            patch(
                "app.modules.robots_v2.backtest.service.create_db_run",
                return_value=901,
            ) as create_mock,
            patch(
                "app.modules.robots_v2.backtest.service.enqueue_background_job",
                return_value="job-uuid",
            ) as enqueue_mock,
        ):
            rec, enqueued = await svc.start(db, user_id=7, request=request)
            return rec, enqueued, create_mock, enqueue_mock

    rec, enqueued, create_mock, enqueue_mock = asyncio.run(_run())

    assert enqueued is True
    assert rec.run_id == 901
    assert rec.robot_id is None
    create_kwargs = create_mock.call_args.kwargs
    assert create_kwargs["robot_id"] is None
    assert create_kwargs["user_id"] == 7
    assert enqueue_mock.call_args.kwargs["payload"]["robot_id"] is None


def test_save_as_robot_success_orphan_attach():
    svc = BacktestService()
    db = MagicMock()
    run_row = {
        "id": 901,
        "robot_id": None,
        "user_id": 7,
        "status": "SUCCESS",
        "config_snapshot": {**_sample_config_dict(), "engine_version": "v2"},
    }
    created = RobotV2Response(
        id=44,
        name="Lab bot",
        type=2,
        tokenId=3,
        status=2,
        configVersion=4,
        config=_sample_config_dict(),
        metadata={},
        createdAt=datetime.now(timezone.utc),
    )

    with (
        patch("app.modules.robots_v2.backtest.service.fetch_db_run", return_value=run_row),
        patch("app.modules.robots_v2.backtest.service.attach_backtest_run_to_robot") as attach_mock,
        patch.object(RobotsV2Service, "create_or_update", return_value=created) as create_mock,
    ):
        out = svc.save_as_robot(
            db,
            user_id=7,
            run_id=901,
            request=RobotV2BacktestSaveAsRobotRequest(name="Lab bot", tokenId=3, attachRun=True),
        )

    assert out.robot_id == 44
    assert out.run_id == 901
    create_mock.assert_called_once()
    create_kwargs = create_mock.call_args.args[2]
    assert create_kwargs.status == 2
    assert "engine_version" not in create_kwargs.config
    attach_mock.assert_called_once_with(db, run_id=901, user_id=7, robot_id=44)
    db.commit.assert_called_once()


def test_save_as_robot_rejects_non_success():
    svc = BacktestService()
    db = MagicMock()
    with patch(
        "app.modules.robots_v2.backtest.service.fetch_db_run",
        return_value={"status": "FAILED", "config_snapshot": _sample_config_dict()},
    ):
        with pytest.raises(HTTPException) as exc:
            svc.save_as_robot(
                db,
                user_id=7,
                run_id=1,
                request=RobotV2BacktestSaveAsRobotRequest(name="X", tokenId=1),
            )
    assert exc.value.status_code == 422


def test_save_as_robot_attach_conflict_when_bound():
    svc = BacktestService()
    db = MagicMock()
    run_row = {
        "status": "SUCCESS",
        "robot_id": 13,
        "config_snapshot": {**_sample_config_dict(), "engine_version": "v2", "v2RobotId": 13},
    }
    with patch("app.modules.robots_v2.backtest.service.fetch_db_run", return_value=run_row):
        with pytest.raises(HTTPException) as exc:
            svc.save_as_robot(
                db,
                user_id=7,
                run_id=1,
                request=RobotV2BacktestSaveAsRobotRequest(name="X", tokenId=1, attachRun=True),
            )
    assert exc.value.status_code == 409


def test_delete_robot_nullifies_soft_bind():
    service = RobotsV2Service()
    db = MagicMock()
    robot = RobotV2Response(
        id=42,
        name="Test",
        type=2,
        tokenId=1,
        status=1,
        configVersion=4,
        config={"core": {"mode": "paper"}},
        metadata={},
        createdAt=datetime.now(timezone.utc),
    )
    db.execute.return_value = MagicMock(fetchone=MagicMock(return_value=MagicMock()))

    with (
        patch.object(service, "get_robot", return_value=robot),
        patch("app.modules.robots_v2.engine.session_manager.session_manager") as sm,
        patch(
            "app.modules.robots_v2.backtest.persist.nullify_robot_soft_bind",
            return_value=2,
        ) as nullify,
    ):
        sm.get.return_value = None
        result = asyncio.run(service.delete_robot(db, user_id=7, robot_id=42))

    assert result == {"id": 42, "deleted": True}
    nullify.assert_called_once_with(db, robot_id=42)
    db.commit.assert_called()
