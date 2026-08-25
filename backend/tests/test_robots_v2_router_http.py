"""HTTP integration tests for /api/v2/robots/* (mocked DB and services)."""

from __future__ import annotations

import inspect
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator
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
from app.modules.robots_v2 import schemas, service
from app.modules.robots_v2.backtest.schemas import (
    RobotV2BacktestCompareResponse,
    RobotV2BacktestDetailsResponse,
    RobotV2BacktestListResponse,
    RobotV2BacktestStatusResponse,
)


def _sample_trading_config() -> dict[str, Any]:
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


def _robot_response(*, robot_id: int = 42) -> schemas.RobotV2Response:
    return schemas.RobotV2Response(
        id=robot_id,
        name="Test",
        type=2,
        tokenId=1,
        status=1,
        configVersion=4,
        config={"core": {"mode": "paper"}},
        metadata={},
        createdAt=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = 7
    user.login = "tester"
    return user


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@contextmanager
def _v2_client(
    mock_user: User,
    mock_db: MagicMock,
    *,
    v2_enabled: bool = True,
) -> Iterator[TestClient]:
    from app.main import app

    async def override_user() -> User:
        return mock_user

    def override_db() -> Iterator[MagicMock]:
        yield mock_db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.modules.robots_v2.router.settings.ROBOTS_V2_ENABLED", v2_enabled):
            yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def auth_client(mock_user: User, mock_db: MagicMock) -> Iterator[TestClient]:
    with _v2_client(mock_user, mock_db, v2_enabled=True) as client:
        yield client


AUTH_HEADERS = {"Authorization": "Bearer test-token"}


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("POST", "/api/v2/robots/data", {}),
        ("POST", "/api/v2/robots/create", {"name": "R", "type": 2, "tokenId": 1, "config": {}}),
        ("GET", "/api/v2/robots/1", None),
        ("POST", "/api/v2/robots/delete", {"robotId": 1}),
        ("POST", "/api/v2/robots/change_status", {"robotId": 1, "status": 0}),
        ("POST", "/api/v2/robots/validate", {"type": 2, "config": {}}),
        ("POST", "/api/v2/robots/audit", {"robotId": 1}),
        ("GET", "/api/v2/robots/backtest/runs", None),
        ("GET", "/api/v2/robots/1/status", None),
    ],
)
def test_v2_routes_require_auth(method: str, path: str, json_body: dict | None) -> None:
    from app.main import app

    with patch("app.modules.robots_v2.router.settings.ROBOTS_V2_ENABLED", True):
        client = TestClient(app)
        kwargs: dict[str, Any] = {}
        if json_body is not None:
            kwargs["json"] = json_body
        response = client.request(method, path, **kwargs)

    assert response.status_code == 401


def test_v2_disabled_returns_404(mock_user: User, mock_db: MagicMock) -> None:
    with _v2_client(mock_user, mock_db, v2_enabled=False) as client:
        response = client.post("/api/v2/robots/data", json={}, headers=AUTH_HEADERS)

    assert response.status_code == 404
    assert "ROBOTS_V2_ENABLED" in response.json()["detail"]


def test_delete_route_is_async_and_delegates_to_service(
    auth_client: TestClient,
    mock_db: MagicMock,
    mock_user: User,
) -> None:
    from app.modules.robots_v2.router import delete_robot

    assert inspect.iscoroutinefunction(delete_robot)

    with patch.object(
        service.robots_v2_service,
        "delete_robot",
        new_callable=AsyncMock,
        return_value={"id": 42, "deleted": True},
    ) as mock_delete:
        response = auth_client.post(
            "/api/v2/robots/delete",
            json={"robotId": 42},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    assert response.json() == {"id": 42, "deleted": True}
    mock_delete.assert_awaited_once_with(mock_db, mock_user.id, 42)


def test_change_status_route_is_async_and_delegates_to_service(
    auth_client: TestClient,
    mock_db: MagicMock,
    mock_user: User,
) -> None:
    from app.modules.robots_v2.router import change_robot_status

    assert inspect.iscoroutinefunction(change_robot_status)

    robot = _robot_response()
    with patch.object(
        service.robots_v2_service,
        "change_status",
        new_callable=AsyncMock,
        return_value=robot,
    ) as mock_change:
        response = auth_client.post(
            "/api/v2/robots/change_status",
            json={"robotId": 42, "status": 0, "stopMode": "hard"},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    assert response.json()["id"] == 42
    mock_change.assert_awaited_once()
    call_args = mock_change.await_args
    assert call_args is not None
    assert call_args.args[0] is mock_db
    assert call_args.args[1] == mock_user.id
    assert call_args.args[2].robot_id == 42
    assert call_args.args[2].status == 0
    assert call_args.args[2].stop_mode == "hard"


def test_list_robots_delegates_to_service(auth_client: TestClient, mock_user: User) -> None:
    robot = _robot_response()
    with patch.object(service.robots_v2_service, "list_robots", return_value=[robot]) as mock_list:
        response = auth_client.post("/api/v2/robots/data", json={}, headers=AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == 42
    mock_list.assert_called_once()
    assert mock_list.call_args.args[1] == mock_user.id


def test_get_robot_delegates_to_service(auth_client: TestClient, mock_user: User) -> None:
    robot = _robot_response(robot_id=5)
    with patch.object(service.robots_v2_service, "get_robot", return_value=robot) as mock_get:
        response = auth_client.get("/api/v2/robots/5", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json()["id"] == 5
    mock_get.assert_called_once_with(mock_get.call_args.args[0], mock_user.id, 5)


def test_audit_post_accepts_valid_payload_shape(auth_client: TestClient, mock_user: User) -> None:
    audit_payload = {
        "robotId": 42,
        "sessions": {"items": [], "total": 0},
        "fills": {"items": [], "total": 0},
    }
    with patch.object(service.robots_v2_service, "query_audit", return_value=audit_payload) as mock_audit:
        response = auth_client.post(
            "/api/v2/robots/audit",
            json={"robotId": 42, "limit": 50, "types": ["sessions", "fills"]},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["robotId"] == 42
    assert body["sessions"]["total"] == 0
    assert body["fills"]["total"] == 0
    mock_audit.assert_called_once()
    request_arg = mock_audit.call_args.args[2]
    assert request_arg.robot_id == 42
    assert request_arg.limit == 50
    assert request_arg.types == ["sessions", "fills"]


def test_backtest_list_runs_returns_200(auth_client: TestClient, mock_user: User) -> None:
    empty = RobotV2BacktestListResponse(items=[], total=0)
    with patch(
        "app.modules.robots_v2.router.backtest_service.list_runs",
        new_callable=AsyncMock,
        return_value=empty,
    ) as mock_list:
        response = auth_client.get("/api/v2/robots/backtest/runs", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json()["total"] == 0
    mock_list.assert_awaited_once()
    assert mock_list.await_args.kwargs["user_id"] == mock_user.id


def test_backtest_start_returns_202_when_enqueued(auth_client: TestClient, mock_user: User) -> None:
    rec = MagicMock(run_id=99)
    with patch(
        "app.modules.robots_v2.router.backtest_service.start",
        new_callable=AsyncMock,
        return_value=(rec, True),
    ) as mock_start:
        response = auth_client.post(
            "/api/v2/robots/backtest",
            json={
                "config": _sample_trading_config(),
                "from_date": "2025-01-01T00:00:00Z",
                "to_date": "2025-02-01T00:00:00Z",
                "asyncExecution": True,
            },
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 202
    assert response.json()["run_id"] == 99
    mock_start.assert_awaited_once()


def test_backtest_status_returns_200(auth_client: TestClient, mock_user: User) -> None:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    status_payload = RobotV2BacktestStatusResponse(
        run_id=10,
        status="running",
        requested_from=now,
        requested_to=now,
        started_at=now,
    )
    with patch(
        "app.modules.robots_v2.router.backtest_service.get_status",
        new_callable=AsyncMock,
        return_value=status_payload,
    ):
        response = auth_client.get(
            "/api/v2/robots/backtest/runs/10/status",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    assert response.json()["run_id"] == 10
    assert response.json()["status"] == "running"


def test_backtest_details_returns_200(auth_client: TestClient) -> None:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    details = RobotV2BacktestDetailsResponse(
        run_id=11,
        status="completed",
        requested_from=now,
        requested_to=now,
        started_at=now,
        finished_at=now,
        total_return_percent=1.5,
    )
    with patch(
        "app.modules.robots_v2.router.backtest_service.get_details",
        new_callable=AsyncMock,
        return_value=details,
    ):
        response = auth_client.get(
            "/api/v2/robots/backtest/runs/11",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    assert response.json()["run_id"] == 11
    assert response.json()["status"] == "completed"


def test_backtest_compare_returns_200(auth_client: TestClient, mock_user: User) -> None:
    compare = RobotV2BacktestCompareResponse(
        base_run_id=1,
        compare_run_id=2,
    )
    with patch(
        "app.modules.robots_v2.router.backtest_service.compare",
        new_callable=AsyncMock,
        return_value=compare,
    ) as mock_compare:
        response = auth_client.post(
            "/api/v2/robots/backtest/compare",
            json={"baseRunId": 1, "compareRunId": 2},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    assert response.json()["base_run_id"] == 1
    mock_compare.assert_awaited_once()
    assert mock_compare.await_args.kwargs["user_id"] == mock_user.id


def test_backtest_cancel_returns_200(auth_client: TestClient, mock_user: User) -> None:
    rec = MagicMock(run_id=7, status="cancelled")
    with patch(
        "app.modules.robots_v2.router.backtest_service.cancel",
        new_callable=AsyncMock,
        return_value=rec,
    ) as mock_cancel:
        response = auth_client.post(
            "/api/v2/robots/backtest/runs/7/cancel",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == 7
    assert body["cancel_requested"] is True
    assert body["status"] == "cancelled"
    mock_cancel.assert_awaited_once_with(7, user_id=mock_user.id, db=mock_cancel.await_args.kwargs["db"])


def test_refresh_universe_route_delegates_to_service(
    auth_client: TestClient,
    mock_db: MagicMock,
    mock_user: User,
) -> None:
    from app.modules.robots_v2.router import refresh_robot_universe

    assert inspect.iscoroutinefunction(refresh_robot_universe)

    payload = {
        "robotId": 42,
        "universe": ["OZON"],
        "added": ["OZON"],
        "removed": ["SBER"],
        "reason": "force",
        "keptPrevious": False,
        "refreshedAt": "2026-08-21T08:00:00+00:00",
        "tickerScan": [],
    }
    with patch.object(
        service.robots_v2_service,
        "refresh_universe",
        new_callable=AsyncMock,
        return_value=payload,
    ) as mock_refresh:
        response = auth_client.post(
            "/api/v2/robots/42/refresh-universe",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["universe"] == ["OZON"]
    assert body["reason"] == "force"
    mock_refresh.assert_awaited_once_with(mock_db, mock_user.id, 42)
