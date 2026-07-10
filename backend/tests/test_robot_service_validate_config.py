from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.robots.service import RobotService


def test_validate_robot_config_payload_returns_normalized_config():
    service = RobotService()
    res = service.validate_robot_config_payload(
        robot_type=2,
        broker_type="tinvest",
        config={
            "strategy": "momentum_breakout",
            "universe_mode": "dms_pipeline",
            "risk": {"stop_loss_percent": 2.0},
        },
    )
    assert res["schema_profile"] == "type2_tinvest"
    normalized = res["normalized_config"]
    assert normalized["config_version"] >= 2
    assert normalized["signal_generation"]["strategy"] == "momentum_breakout"


def test_validate_robot_config_payload_returns_422_on_error():
    service = RobotService()
    with pytest.raises(HTTPException) as exc:
        service.validate_robot_config_payload(
            robot_type=2,
            broker_type="bybit",
            config={"strategy": "momentum_breakout"},
        )
    assert exc.value.status_code == 422
    assert "Некорректный config" in str(exc.value.detail)
