"""Lifecycle fixes: delete/change_status stop sessions; WS stream auth."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.testclient import TestClient

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.schemas import RobotV2ChangeStatusRequest, RobotV2Response
from app.modules.robots_v2.service import RobotsV2Service


def _trading_robot(*, robot_id: int = 42, metadata: dict | None = None) -> RobotV2Response:
    return RobotV2Response(
        id=robot_id,
        name="Test",
        type=2,
        tokenId=1,
        status=1,
        configVersion=4,
        config={"core": {"mode": "paper"}},
        metadata=metadata or {},
        createdAt=datetime.now(timezone.utc),
    )


def test_delete_robot_stops_active_session():
    service = RobotsV2Service()
    db = MagicMock()
    robot = _trading_robot()
    mock_session = MagicMock()

    with patch.object(service, "get_robot", return_value=robot), patch(
        "app.modules.robots_v2.engine.session_manager.session_manager"
    ) as sm:
        sm.get.return_value = mock_session
        sm.stop = AsyncMock()
        db.execute.return_value = MagicMock(fetchone=MagicMock(return_value=MagicMock()))

        result = asyncio.run(service.delete_robot(db, user_id=7, robot_id=42))

    assert result == {"id": 42, "deleted": True}
    sm.get.assert_called_once_with(42)
    sm.stop.assert_awaited_once_with(42, stop_mode="hard")
    db.commit.assert_called_once()
    soft_delete_call = db.execute.call_args
    assert "UPDATE" in str(soft_delete_call.args[0])
    assert "deletedAt" in str(soft_delete_call.kwargs.get("metadata") or soft_delete_call.args[1].get("metadata", ""))


def test_delete_robot_skips_stop_when_no_session():
    service = RobotsV2Service()
    db = MagicMock()
    robot = _trading_robot()

    with patch.object(service, "get_robot", return_value=robot), patch(
        "app.modules.robots_v2.engine.session_manager.session_manager"
    ) as sm:
        sm.get.return_value = None
        sm.stop = AsyncMock()
        db.execute.return_value = MagicMock(fetchone=MagicMock(return_value=MagicMock()))

        asyncio.run(service.delete_robot(db, user_id=7, robot_id=42))

    sm.stop.assert_not_called()


def test_change_status_disable_stops_active_session_with_stop_mode():
    service = RobotsV2Service()
    db = MagicMock()
    robot = _trading_robot(metadata={"sessionDesired": "running"})
    updated_row = MagicMock()
    mock_session = MagicMock()

    def _execute(stmt, params=None):
        sql = str(stmt)
        if "UPDATE" in sql and "metadata" in sql:
            return MagicMock()
        if "build_update_status_query" in sql or "status" in sql.lower():
            return MagicMock(fetchone=MagicMock(return_value=updated_row))
        return MagicMock(fetchone=MagicMock(return_value=updated_row))

    db.execute.side_effect = _execute

    with patch.object(service, "get_robot", side_effect=[robot, robot]), patch(
        "app.modules.robots_v2.engine.session_manager.session_manager"
    ) as sm:
        sm.get.return_value = mock_session
        sm.stop = AsyncMock()
        request = RobotV2ChangeStatusRequest(robotId=42, status=2, stopMode="hard")

        result = asyncio.run(service.change_status(db, user_id=7, request=request))

    sm.get.assert_called_once_with(42)
    sm.stop.assert_awaited_once_with(42, stop_mode="hard")
    assert result.id == 42


def test_change_status_enable_does_not_stop_session():
    service = RobotsV2Service()
    db = MagicMock()
    robot = _trading_robot()
    updated_row = MagicMock()
    db.execute.return_value = MagicMock(fetchone=MagicMock(return_value=updated_row))

    with patch.object(service, "get_robot", side_effect=[robot, robot]), patch(
        "app.modules.robots_v2.engine.session_manager.session_manager"
    ) as sm:
        sm.get.return_value = MagicMock()
        sm.stop = AsyncMock()
        request = RobotV2ChangeStatusRequest(robotId=42, status=1)

        asyncio.run(service.change_status(db, user_id=7, request=request))

    sm.stop.assert_not_called()


def test_robot_stream_ws_rejects_missing_token():
    from app.main import app

    with patch("app.modules.robots_v2.router.settings.ROBOTS_V2_ENABLED", True), patch(
        "app.modules.robots_v2.router.authenticate_ws_user_id",
        return_value=None,
    ):
        client = TestClient(app)
        with client.websocket_connect("/api/v2/robots/1/stream") as ws:
            payload = ws.receive_json()
            assert payload == {"type": "error", "message": "Unauthorized"}


def test_robot_stream_ws_rejects_unknown_robot():
    from app.main import app

    with patch("app.modules.robots_v2.router.settings.ROBOTS_V2_ENABLED", True), patch(
        "app.modules.robots_v2.router.authenticate_ws_user_id",
        return_value=99,
    ), patch.object(
        RobotsV2Service,
        "get_robot",
        side_effect=HTTPException(status_code=404, detail="Robot not found"),
    ):
        client = TestClient(app)
        with client.websocket_connect("/api/v2/robots/1/stream?token=good") as ws:
            payload = ws.receive_json()
            assert payload == {"type": "error", "message": "Robot not found"}
