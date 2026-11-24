"""Manual order helpers (legacy RobotService path removed in Wave 3)."""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robot_lib.schemas import RobotManualOrderRequest
from app.modules.robot_lib.trading.manual_order import (
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
