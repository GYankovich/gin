"""schedule_policy — этап 5 BRD-ARCH-04."""

from __future__ import annotations

from datetime import datetime, timezone

from app.modules.robots.scheduling.schedule_policy import (
    inside_schedule_window,
    should_start_trading_session,
)


def _utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_no_schedule_allows_start():
    assert should_start_trading_session({"config": {}}) is True


def test_weekday_mask_blocks_saturday():
    # 2024-06-01 = Saturday; mask 31 = Mon-Fri only
    robot = {
        "schedule_type": 2,
        "start_time": "10:00:00+03:00",
        "end_time": "18:45:00+03:00",
        "weekdays": 31,
    }
    sat = _utc(2024, 6, 1, 8, 0)  # 11:00 MSK
    assert should_start_trading_session(robot, now=sat) is False


def test_time_window_msk_inside():
    robot = {
        "schedule_type": 2,
        "start_time": "10:00:00+03:00",
        "end_time": "18:45:00+03:00",
        "weekdays": 31,
    }
    # 2024-06-03 Monday 07:30 UTC = 10:30 MSK
    mon = _utc(2024, 6, 3, 7, 30)
    assert should_start_trading_session(robot, now=mon) is True


def test_time_window_msk_outside():
    robot = {
        "schedule_type": 2,
        "start_time": "10:00:00+03:00",
        "end_time": "18:45:00+03:00",
        "weekdays": 31,
    }
    # 05:00 UTC = 08:00 MSK — до открытия
    mon = _utc(2024, 6, 3, 5, 0)
    assert should_start_trading_session(robot, now=mon) is False


def test_risk_fallback_from_config():
    robot = {
        "config": {
            "risk": {
                "trading_hours_start": "10:00 MSK",
                "trading_hours_end": "18:45 MSK",
                "allowed_weekdays": 31,
            }
        }
    }
    mon = _utc(2024, 6, 3, 7, 30)
    assert should_start_trading_session(robot, now=mon) is True


def test_inside_schedule_window_none():
    assert inside_schedule_window(_utc(2024, 6, 3, 12, 0), None) is True


def test_schedule_type_1_ignores_weekdays_and_is_always_open():
    sat = _utc(2024, 6, 1, 8, 0)  # Saturday
    robot = {
        "schedule_type": 1,
        "weekdays": 31,  # Mon-Fri mask; should be ignored for type=1
    }
    assert should_start_trading_session(robot, now=sat) is True


def test_bybit_without_schedule_defaults_to_always_on():
    sat = _utc(2024, 6, 1, 8, 0)  # Saturday
    robot = {
        "config": {
            "broker_type": "bybit",
            "risk": {
                "trading_hours_start": "10:00 MSK",
                "trading_hours_end": "18:45 MSK",
                "allowed_weekdays": 31,
            },
        }
    }
    assert should_start_trading_session(robot, now=sat) is True
