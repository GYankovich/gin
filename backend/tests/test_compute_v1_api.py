"""HTTP tests for ARCH-05 Phase C /api/compute/v1."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.core.database import get_db
from app.core.security import get_current_user
from app.modules.auth.models import User
from app.modules.robots_v2.backtest.schemas import (
    RobotV2BacktestListResponse,
    RobotV2BacktestStatusResponse,
)
from app.modules.robots_v2.backtest.store import BacktestRunRecord


def _sample_config() -> dict[str, Any]:
    return {
        "configVersion": 4,
        "core": {
            "goal": "moderate",
            "instrumentType": "stock",
            "mode": "paper",
            "advancedMode": False,
            "schedule": {
                "weekdays": [True] * 7,
                "timeFrom": "10:00",
                "timeTo": "18:30",
                "pollInterval": "5m",
            },
        },
        "strategy": {
            "archetype": "momentum",
            "timeframe": "1h",
            "params": {"maPeriod": 50, "volumeMultiplier": 2.0},
        },
        "universe": {
            "mode": "fixed",
            "fixedList": ["SBER"],
            "excluded": [],
            "maxAssets": 20,
            "exitOnDrop": False,
        },
        "risk": {
            "capital": 100_000,
            "maxPositionSharePct": 10,
            "stopLossPct": 2,
            "takeProfitPct": 4,
            "maxDailyLoss": 5000,
            "maxDrawdownPct": 50,
            "maxConcurrentPositions": 3,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
            "slippagePct": 0.5,
            "stopMode": "soft",
        },
    }


@pytest.fixture
def client():
    from app.main import app

    user = MagicMock(spec=User)
    user.id = 1
    user.login = "u"

    async def _user():
        return user

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_compute_create_run_202(client: TestClient):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rec = BacktestRunRecord(
        run_id=216,
        user_id=1,
        robot_id=13,
        status="QUEUED",
        requested_from=now,
        requested_to=now,
        started_at=now,
        finished_at=None,
        initial_capital=100_000,
        config_snapshot={},
    )
    with patch(
        "app.modules.compute.service.backtest_service.start",
        new=AsyncMock(return_value=(rec, True)),
    ), patch(
        "app.modules.compute.service.find_background_job_for_backtest_run",
        return_value={"id": "11111111-1111-1111-1111-111111111111"},
    ):
        resp = client.post(
            "/api/compute/v1/runs",
            json={
                "config": _sample_config(),
                "from_date": "2026-01-01T00:00:00Z",
                "to_date": "2026-01-10T00:00:00Z",
                "initial_capital": 100000,
                "robot_id": 13,
                "priority": "interactive",
            },
            headers={"Idempotency-Key": "smoke-1"},
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"] == 216
    assert body["status"] == "queued"
    assert body["job_id"]
    assert "/api/compute/v1/runs/216" in body["message"]


def test_compute_get_status_and_cancel(client: TestClient):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    status_payload = RobotV2BacktestStatusResponse(
        run_id=7,
        robot_id=1,
        status="RUNNING",
        requested_from=now,
        requested_to=now,
        started_at=now,
        finished_at=None,
        initial_capital=100_000,
        progress_percent=10.0,
    )
    cancel_rec = BacktestRunRecord(
        run_id=7,
        user_id=1,
        robot_id=1,
        status="RUNNING",
        requested_from=now,
        requested_to=now,
        started_at=now,
        finished_at=None,
        initial_capital=100_000,
        config_snapshot={},
        cancel_requested=True,
    )
    with patch(
        "app.modules.compute.service.backtest_service.get_status",
        new=AsyncMock(return_value=status_payload),
    ):
        r1 = client.get("/api/compute/v1/runs/7/status")
    assert r1.status_code == 200
    assert r1.json()["status"] == "RUNNING"

    with patch(
        "app.modules.compute.service.backtest_service.cancel",
        new=AsyncMock(return_value=cancel_rec),
    ):
        r2 = client.post("/api/compute/v1/runs/7/cancel")
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["status"] == "cancel_requested"


def test_compute_queue_metrics(client: TestClient):
    with patch(
        "app.modules.compute.service.count_lane_jobs_by_status",
        return_value={"queued": 2, "running": 1},
    ):
        resp = client.get("/api/compute/v1/metrics/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lane"] == "heavy"
    assert body["queued"] == 2
    assert body["running"] == 1


def test_compute_list_runs(client: TestClient):
    payload = RobotV2BacktestListResponse(items=[], total=0)
    with patch(
        "app.modules.compute.service.backtest_service.list_runs",
        new=AsyncMock(return_value=payload),
    ):
        resp = client.get("/api/compute/v1/runs?robot_id=13&limit=10")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
