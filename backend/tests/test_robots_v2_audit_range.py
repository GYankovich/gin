"""Audit history window: half-open SQL range on fills, orders, and cycles."""

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from datetime import datetime, timezone

from app.modules.robots_v2.audit_queries import (
    build_count_cycles_query,
    build_count_fills_query,
    build_count_orders_query,
    build_list_cycles_query,
    build_list_fills_query,
    build_list_orders_query,
)
from app.modules.robots_v2.schemas import RobotV2AuditRequest

START = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)
END = datetime(2026, 10, 22, 21, 0, tzinfo=timezone.utc)


def test_audit_request_accepts_from_to_aliases():
    req = RobotV2AuditRequest.model_validate({
        "robotId": 3,
        "from": "2026-10-01T21:00:00Z",
        "to": "2026-10-22T21:00:00Z",
        "types": ["fills"],
    })
    assert req.from_at is not None and req.to_at is not None
    assert req.from_at < req.to_at


def test_fills_range_is_half_open_and_optional():
    query, params = build_list_fills_query(
        robot_id=1, user_id=2, limit=500, from_at=START, to_at=END,
    )
    assert "f.filled_at >= :from_at" in query
    assert "f.filled_at < :to_at" in query
    assert "ORDER BY f.filled_at DESC" in query
    assert params["from_at"] == START
    assert params["to_at"] == END

    plain, plain_params = build_list_fills_query(robot_id=1, user_id=2, limit=100)
    assert "from_at" not in plain
    assert "from_at" not in plain_params

    count_q, count_params = build_count_fills_query(
        robot_id=1, user_id=2, from_at=START, to_at=END,
    )
    assert "f.filled_at >= :from_at" in count_q
    assert "f.filled_at < :to_at" in count_q
    assert count_params["to_at"] == END


def test_orders_and_cycles_use_their_timestamp_columns():
    orders_q, _ = build_list_orders_query(
        robot_id=1, user_id=2, limit=500, from_at=START, to_at=END,
    )
    assert "o.submitted_at >= :from_at" in orders_q
    assert "o.submitted_at < :to_at" in orders_q
    orders_count, _ = build_count_orders_query(
        robot_id=1, user_id=2, from_at=START, to_at=END,
    )
    assert "o.submitted_at < :to_at" in orders_count

    cycles_q, _ = build_list_cycles_query(
        robot_id=1, user_id=2, limit=500, from_at=START, to_at=END,
    )
    assert "c.started_at >= :from_at" in cycles_q
    assert "c.started_at < :to_at" in cycles_q
    cycles_count, _ = build_count_cycles_query(
        robot_id=1, user_id=2, to_at=END,
    )
    assert "c.started_at < :to_at" in cycles_count
    assert "from_at" not in cycles_count


def test_fifo_timeline_can_cap_at_to_without_from():
    query, params = build_list_fills_query(
        robot_id=1, user_id=2, limit=10_000, to_at=END,
    )
    assert "f.filled_at < :to_at" in query
    assert "from_at" not in query
    assert "from_at" not in params
    assert query.replace("ORDER BY f.filled_at DESC", "ORDER BY f.filled_at ASC") != query
