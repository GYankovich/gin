"""Manual live limit order: qty/notional resolve + service path."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robots.schemas import RobotManualOrderRequest
from app.modules.robots.service import RobotService
from app.modules.robots.trading.manual_order import (
    format_manual_broker_reject,
    resolve_manual_order_quantity,
)


def test_resolve_manual_order_quantity_from_qty():
    assert resolve_manual_order_quantity(price=10.0, quantity=2.5) == 2.5


def test_resolve_manual_order_quantity_from_notional():
    assert resolve_manual_order_quantity(price=0.05, notional=10.0) == 200.0


def test_resolve_manual_order_quantity_rejects_both_or_neither():
    with pytest.raises(ValueError):
        resolve_manual_order_quantity(price=1.0, quantity=1.0, notional=2.0)
    with pytest.raises(ValueError):
        resolve_manual_order_quantity(price=1.0)


def test_format_manual_broker_reject_110007():
    msg = format_manual_broker_reject(
        Exception("ByBit API error retCode=110007: ab not enough for new order"),
        free_funds=1.23,
    )
    assert "110007" in msg
    assert "свободного баланса" in msg
    assert "1.23" in msg


def test_manual_order_schema_xor_size():
    ok = RobotManualOrderRequest(
        robotId=24, figi="TREEUSDT", side="BUY", price=0.04, quantity=100
    )
    assert ok.quantity == 100
    with pytest.raises(ValidationError):
        RobotManualOrderRequest(robotId=24, figi="TREEUSDT", side="BUY", price=0.04)
    with pytest.raises(ValidationError):
        RobotManualOrderRequest(
            robotId=24, figi="TREEUSDT", side="BUY", price=0.04, quantity=1, notional=5
        )


def test_place_manual_live_order_calls_broker_post_order():
    svc = RobotService()
    db = MagicMock()

    robot = {
        "id": 24,
        "type": 2,
        "config": {"broker_type": "bybit", "account_id": "acct-1", "bybit": {"instrument_category": "linear"}},
        "token": {"id": 7, "status": 1, "type": 3},
    }
    broker = MagicMock()
    broker.post_order = AsyncMock(
        return_value={"orderId": "oid-1", "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW"}
    )

    with patch.object(svc, "get_robot_by_id", AsyncMock(return_value=robot)), patch(
        "app.modules.robots.service.token_service.get_token_by_id",
        AsyncMock(return_value={"token": "secret", "extra_data": {}}),
    ), patch(
        "app.modules.robots.trading.brokers.create_broker_facade",
        return_value=broker,
    ), patch(
        "app.modules.robots.service._resolve_robot_account_id",
        AsyncMock(return_value="acct-1"),
    ), patch(
        "app.modules.robots.trading.brokers.routing.enforce_broker_for_token",
        return_value="bybit",
    ), patch(
        "app.modules.robots.live_events.insert_session_log",
        return_value=1,
    ), patch(
        "app.modules.robots.live_events.uses_postgres_live_events",
        return_value=False,
    ), patch(
        "app.modules.portfolio.order_registry.resolve_portfolio_account_pk",
        return_value=7,
    ), patch(
        "app.modules.portfolio.order_registry.insert_pending_order",
        return_value=55,
    ) as ins, patch(
        "app.modules.portfolio.order_registry.update_order_by_pk",
        return_value=True,
    ) as upd:
        result = asyncio.run(
            svc.place_manual_live_order(
                db,
                user_id=1,
                robot_id=24,
                figi="treeusdt",
                side="BUY",
                price=0.04,
                notional=8.0,
                reduce_only=False,
            )
        )

    broker.post_order.assert_awaited_once()
    kwargs = broker.post_order.await_args.kwargs
    assert kwargs["figi"] == "TREEUSDT"
    assert kwargs["quantity"] == 200.0
    assert result["order_id"] == "oid-1"
    assert result.get("account_order_id") == 55
    assert ins.called
    assert upd.called
    assert upd.call_args.kwargs.get("order_id") == "oid-1"


def test_place_manual_live_order_marks_rejected_on_broker_error():
    svc = RobotService()
    db = MagicMock()
    robot = {
        "id": 24,
        "type": 2,
        "config": {"broker_type": "bybit", "account_id": "acct-1"},
        "token": {"id": 7, "status": 1, "type": 3},
    }
    broker = MagicMock()
    broker.post_order = AsyncMock(side_effect=Exception("retCode=110007"))
    broker.get_free_funds = AsyncMock(return_value=1.0)

    with patch.object(svc, "get_robot_by_id", AsyncMock(return_value=robot)), patch(
        "app.modules.robots.service.token_service.get_token_by_id",
        AsyncMock(return_value={"token": "secret", "extra_data": {}}),
    ), patch(
        "app.modules.robots.trading.brokers.create_broker_facade",
        return_value=broker,
    ), patch(
        "app.modules.robots.service._resolve_robot_account_id",
        AsyncMock(return_value="acct-1"),
    ), patch(
        "app.modules.robots.trading.brokers.routing.enforce_broker_for_token",
        return_value="bybit",
    ), patch(
        "app.modules.portfolio.order_registry.resolve_portfolio_account_pk",
        return_value=7,
    ), patch(
        "app.modules.portfolio.order_registry.insert_pending_order",
        return_value=55,
    ), patch(
        "app.modules.portfolio.order_registry.update_order_by_pk",
        return_value=True,
    ) as upd:
        with pytest.raises(HTTPException) as ei:
            asyncio.run(
                svc.place_manual_live_order(
                    db,
                    user_id=1,
                    robot_id=24,
                    figi="XLMUSDT",
                    side="BUY",
                    price=0.2,
                    quantity=10.0,
                )
            )
    assert ei.value.status_code == 400
    assert upd.call_args.kwargs.get("status") == "rejected"


def test_place_manual_live_order_rejects_non_trading_robot():
    svc = RobotService()
    db = MagicMock()
    with patch.object(
        svc,
        "get_robot_by_id",
        AsyncMock(return_value={"id": 1, "type": 1, "token": {"id": 1, "status": 1}}),
    ):
        with pytest.raises(HTTPException) as ei:
            asyncio.run(
                svc.place_manual_live_order(
                    db,
                    user_id=1,
                    robot_id=1,
                    figi="AAA",
                    side="BUY",
                    price=1.0,
                    quantity=1.0,
                )
            )
    assert ei.value.status_code == 400
