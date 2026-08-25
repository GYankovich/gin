from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from app.modules.robots_v2.queries import build_get_robot_query, build_list_robots_query
from app.modules.robots_v2.service import RobotsV2Service


def test_create_robot_defaults_status_enabled():
    service = RobotsV2Service()
    db = MagicMock()
    captured: dict[str, Any] = {}

    def _execute(stmt, params=None):
        sql = str(stmt)
        prm = dict(params or {})
        if "INSERT INTO" in sql and ".robots_v2" in sql:
            captured.update(prm)
            return MagicMock(fetchone=MagicMock(return_value=MagicMock(id=55)))
        if "SELECT COALESCE(MAX(version)" in sql:
            return MagicMock(fetchone=MagicMock(return_value=MagicMock(next_version=1)))
        return MagicMock()

    db.execute.side_effect = _execute

    from app.modules.robots_v2.schemas import RobotV2CreateRequest

    config = {
        "configVersion": 4,
        "schedule": {
            "weekdays": [True, True, True, True, True, False, False],
            "timeFrom": "10:00",
            "timeTo": "18:45",
            "pollInterval": "5m",
        },
    }
    with patch.object(service, "_validate_config", return_value=MagicMock(valid=True)):
        with patch.object(service, "get_robot") as mock_get:
            mock_get.return_value = MagicMock(type=2, metadata={})
            service.create_or_update(
                db,
                user_id=1,
                request=RobotV2CreateRequest(
                    name="T",
                    type=2,
                    tokenId=3,
                    config=config,
                ),
            )

    assert captured.get("status") == 1


def test_list_and_get_queries_use_v2_last_started():
    list_sql, _ = build_list_robots_query(user_id=1, schema="public")
    get_sql, _ = build_get_robot_query(robot_id=5, user_id=1, schema="public")
    assert "hide_from_ui" in list_sql
    assert "COALESCE(ds.hide_from_ui, 0) != 1" in list_sql
    for sql in (list_sql, get_sql):
        assert "r.last_started" in sql
        assert "legacyRobotId" not in sql


def test_v4_weekdays_to_mask_and_poll_interval():
    service = RobotsV2Service()
    assert service._v4_weekdays_to_mask([True, True, True, True, True, False, False]) == 31
    assert service._v4_weekdays_to_mask([True, False, False, False, False, False, False]) == 1
    assert service._v4_weekdays_to_mask(None) == 31
    assert service._v4_poll_interval_seconds("1m") == 60
    assert service._v4_poll_interval_seconds("5m") == 300
    assert service._v4_poll_interval_seconds("15m") == 900
    assert service._v4_poll_interval_seconds("1h") == 3600
    assert service._v4_poll_interval_seconds("bogus") == 300
