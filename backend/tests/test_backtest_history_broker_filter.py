"""Tests for backtest history broker_type filter (T0.8)."""

from __future__ import annotations

from app.modules.robots.schemas import RobotBacktestHistoryItem, RobotBacktestHistoryRequest


def test_history_request_broker_type_optional():
    req = RobotBacktestHistoryRequest(limit=10)
    assert req.broker_type is None

    req2 = RobotBacktestHistoryRequest(limit=5, broker_type="bybit")
    assert req2.broker_type == "bybit"


def test_history_item_broker_fields():
    from datetime import datetime, timezone

    item = RobotBacktestHistoryItem(
        id=1,
        broker_type="bybit",
        market_profile="crypto",
        requested_from=datetime.now(timezone.utc),
        requested_to=datetime.now(timezone.utc),
        initial_capital=10_000,
        final_equity=10_500,
        total_return_percent=5.0,
        created_at=datetime.now(timezone.utc),
        result_payload={},
    )
    assert item.broker_type == "bybit"
    assert item.market_profile == "crypto"
