from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.modules.robots.config.profiles import dump_robot_config, validate_robot_config
from app.modules.robots.service import RobotService


def test_create_type1_bybit_config_validates():
    raw = {
        "config_version": 3,
        "schema_profile": "type1_bybit",
        "broker_type": "bybit",
        "bybit": {"testnet": False, "account_type": "UNIFIED"},
    }
    model = validate_robot_config(robot_type=1, raw=raw, broker_type="bybit")
    dumped = dump_robot_config(model)
    assert dumped["schema_profile"] == "type1_bybit"
    assert dumped["broker_type"] == "bybit"
    assert dumped["bybit"]["account_type"] == "UNIFIED"


def test_bootstrap_portfolio_robot_persists_config_and_schedule():
    service = RobotService()
    db = MagicMock()
    executed: list[tuple[str, dict]] = []

    def _capture_execute(stmt, params=None):
        executed.append((str(stmt), dict(params or {})))
        return MagicMock()

    db.execute.side_effect = _capture_execute

    asyncio.run(
        service._bootstrap_portfolio_robot(
            db,
            robot_id=17,
            user_id=1,
            config={
                "config_version": 3,
                "schema_profile": "type1_bybit",
                "broker_type": "bybit",
                "bybit": {"testnet": True, "account_type": "UNIFIED"},
            },
            poll_interval_hours=0.0833,
            trading_hours_start="00:00",
            trading_hours_end="23:59",
            allowed_weekdays=127,
        )
    )

    assert len(executed) == 3
    update_sql, update_params = executed[0]
    assert "UPDATE" in update_sql and "robots" in update_sql
    stored_cfg = json.loads(update_params["config"])
    assert stored_cfg["schema_profile"] == "type1_bybit"
    assert stored_cfg["bybit"]["testnet"] is True

    disable_sql, _ = executed[1]
    assert "robot_schedules" in disable_sql and "is_active = 0" in disable_sql

    insert_sql, insert_params = executed[2]
    assert "INSERT INTO" in insert_sql and "robot_schedules" in insert_sql
    assert insert_params["robot_id"] == 17
    assert insert_params["interval_seconds"] == 300
    assert insert_params["weekdays"] == 127

