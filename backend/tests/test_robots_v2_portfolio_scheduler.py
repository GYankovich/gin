from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.robots.portfolio.queries import build_get_active_portfolio_v2_robots_query
from app.modules.robots.portfolio.schedule import poll_interval_seconds, should_run_portfolio
from app.modules.robots.queries import build_get_robot_query, build_list_robots_query


def test_portfolio_v2_query_reads_robots_v2_not_legacy():
    sql = build_get_active_portfolio_v2_robots_query(schema="public")
    assert "robots" in sql
    assert "robots r" not in sql.replace("robots", "")
    assert "robot_schedules" not in sql


def test_list_and_get_queries_use_v2_last_started_only():
    list_sql, _ = build_list_robots_query(user_id=1, schema="public")
    get_sql, _ = build_get_robot_query(robot_id=5, user_id=1, schema="public")
    for sql in (list_sql, get_sql):
        assert "r.last_started" in sql
        assert "legacyRobotId" not in sql
        assert "legacy.last_started" not in sql


def test_fleet_live_uses_portfolio_snapshots():
    from app.modules.robots.queries import (
        build_fleet_latest_snapshot_query,
        build_fleet_snapshot_curve_query,
        build_fleet_trade_stats_query,
    )

    latest_sql, _ = build_fleet_latest_snapshot_query(user_id=1, schema="public")
    curve_sql, curve_params = build_fleet_snapshot_curve_query(user_id=1, schema="public")

    assert "portfolio_snapshots" in latest_sql
    assert "portfolio_positions" in latest_sql
    assert "portfolio_operations" in latest_sql
    assert "own_funds" in latest_sql
    assert "token_portfolio_accounts" in latest_sql
    assert "portfolio_snapshot_daily" in curve_sql
    assert curve_params["snapshot_days"] == 30
    trades_sql, trades_params = build_fleet_trade_stats_query(user_id=1, schema="public")
    assert "robot_fills" in trades_sql
    assert trades_params["snapshot_days"] == 30


def test_fleet_accounts_come_from_token_membership():
    list_sql, _ = build_list_robots_query(user_id=1, schema="public")
    assert "token_portfolio_accounts" in list_sql
    assert "tpa.token_id = r.token_id" in list_sql
    assert "tpa.status = 1" in list_sql
    assert "pa.last_token_id = r.token_id" not in list_sql


def test_should_run_portfolio_respects_poll_interval():
    config = {
        "schedule": {
            "weekdays": [True, True, True, True, True, False, False],
            "timeFrom": "00:00",
            "timeTo": "23:59",
            "pollInterval": "5m",
        }
    }
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    recent = now - timedelta(seconds=30)
    ok, reason = should_run_portfolio(config, recent, now=now)
    assert ok is False
    assert reason is not None
    assert "300" in reason

    old = now - timedelta(seconds=400)
    ok2, reason2 = should_run_portfolio(config, old, now=now)
    assert ok2 is True
    assert reason2 is None


def test_poll_interval_seconds_mapping():
    assert poll_interval_seconds("1m") == 60
    assert poll_interval_seconds("5m") == 300
    assert poll_interval_seconds("unknown") == 300
