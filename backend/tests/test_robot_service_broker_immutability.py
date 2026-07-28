from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.modules.robots import schemas
from app.modules.robots.service import RobotService


def test_update_robot_rejects_broker_type_change_with_409():
    service = RobotService()
    service.get_robot_by_id = AsyncMock(
        return_value={
            "id": 10,
            "type": 2,
            "config": {"broker_type": "tinvest", "risk": {}},
        }
    )
    db = MagicMock()
    patch = schemas.RobotUpdate(config={"broker_type": "bybit"})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            service.update_robot(
                db=db,
                robot_id=10,
                user_id=1,
                patch=patch,
            )
        )

    assert exc.value.status_code == 409
    assert "broker_type" in str(exc.value.detail)
    db.execute.assert_not_called()


def test_update_robot_config_rejects_broker_type_change_with_409():
    service = RobotService()
    service.get_robot_by_id = AsyncMock(
        return_value={
            "id": 11,
            "type": 2,
            "config": {"broker_type": "tinvest", "risk": {}},
        }
    )
    db = MagicMock()
    config = {"broker_type": "bybit", "risk": {}}

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            service.update_robot_config(
                db=db,
                robot_id=11,
                user_id=1,
                config=config,
            )
        )

    assert exc.value.status_code == 409
    assert "broker_type" in str(exc.value.detail)
    db.execute.assert_not_called()
