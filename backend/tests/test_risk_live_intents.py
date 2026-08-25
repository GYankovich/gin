"""RiskManager live helpers: SL/TP intents + strategy sizing."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robots.trading.risk.manager import (
    RiskManager,
    decide_take_profit_order,
    should_skip_take_profit,
)
from app.modules.robots.trading.costs import calculate_take_profit_price


def test_plan_sl_tp_exit_intents_take_profit_when_reached():
    intents = RiskManager.plan_sl_tp_exit_intents(
        [{"id": 1, "figi": "TREEUSDT", "side": "buy", "quantity": 10, "entry_price": 1.0}],
        {"TREEUSDT": 1.05},
        {
            "stop_loss_percent": 2,
            "take_profit_percent": 3,
            "min_hold_seconds": 0,
            "min_tp_move_bps": 0,
        },
        cost_kw={"broker_commission_rate": 0.0006, "ndfl_rate": 0.0},
    )
    assert len(intents) == 1
    assert intents[0].kind == "exit_sl_tp"
    assert intents[0].reduce_only is True
    assert intents[0].reason == "take_profit"
    assert intents[0].side == "SELL"
    assert intents[0].order_type == "MARKET"


def test_plan_sl_tp_no_order_right_after_entry():
    """Even with tiny TP%, must not arm LIMIT immediately after buy."""
    intents = RiskManager.plan_sl_tp_exit_intents(
        [{"id": 1, "figi": "TREEUSDT", "side": "buy", "quantity": 10, "entry_price": 100.0}],
        {"TREEUSDT": 100.05},  # +5 bps — nowhere near TP
        {
            "stop_loss_percent": 0.99,
            "take_profit_percent": 1.0,
            "min_hold_seconds": 0,
            "min_tp_move_bps": 0,
            "tp_arm_ratio": 0.90,
            "tp_approach_bps": 15,
        },
        cost_kw={"broker_commission_rate": 0.0, "ndfl_rate": 0.0},
    )
    assert intents == []


def test_plan_sl_tp_no_order_while_far_from_tp():
    intents = RiskManager.plan_sl_tp_exit_intents(
        [{"id": 1, "figi": "TREEUSDT", "side": "buy", "quantity": 10, "entry_price": 1.0}],
        {"TREEUSDT": 1.001},
        {
            "stop_loss_percent": 2,
            "take_profit_percent": 3,
            "min_hold_seconds": 0,
            "min_tp_move_bps": 0,
            "tp_arm_ratio": 0.90,
            "tp_approach_bps": 15,
        },
        cost_kw={"broker_commission_rate": 0.0, "ndfl_rate": 0.0},
    )
    assert intents == []


def test_plan_sl_tp_limit_when_near_tp_after_progress():
    tp_price = calculate_take_profit_price(
        1.0, 3, is_long=True, broker_commission_rate=0.0, ndfl_rate=0.0,
    )
    # ~95% of the way to TP
    near = 1.0 + 0.95 * (tp_price - 1.0)
    intents = RiskManager.plan_sl_tp_exit_intents(
        [{"id": 1, "figi": "TREEUSDT", "side": "buy", "quantity": 10, "entry_price": 1.0}],
        {"TREEUSDT": near},
        {
            "stop_loss_percent": 2,
            "take_profit_percent": 3,
            "min_hold_seconds": 0,
            "min_tp_move_bps": 0,
            "tp_arm_ratio": 0.90,
            "tp_approach_bps": 50,
        },
        cost_kw={"broker_commission_rate": 0.0, "ndfl_rate": 0.0},
    )
    assert len(intents) == 1
    assert intents[0].reason == "take_profit"
    assert intents[0].order_type == "LIMIT"
    assert intents[0].price == tp_price


def test_decide_take_profit_not_armed_at_entry():
    tp = calculate_take_profit_price(100.0, 1.0, is_long=True, ndfl_rate=0.0)
    assert decide_take_profit_order(
        entry_price=100.0,
        current_price=100.0,
        take_profit=tp,
        is_long=True,
        risk_params={"tp_arm_ratio": 0.9, "tp_approach_bps": 15},
    ) is None


def test_plan_sl_tp_skips_soft_tp_within_min_hold():
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    created = now - timedelta(seconds=30)
    intents = RiskManager.plan_sl_tp_exit_intents(
        [{
            "id": 1,
            "figi": "TREEUSDT",
            "side": "buy",
            "quantity": 10,
            "entry_price": 1.0,
            "created_at": created,
        }],
        {"TREEUSDT": 1.05},
        {
            "stop_loss_percent": 2,
            "take_profit_percent": 3,
            "min_hold_seconds": 120,
            "min_tp_move_bps": 0,
        },
        cost_kw={"broker_commission_rate": 0.0, "ndfl_rate": 0.0},
        now=now,
    )
    assert intents == []


def test_plan_sl_tp_allows_stop_loss_during_min_hold():
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    created = now - timedelta(seconds=10)
    intents = RiskManager.plan_sl_tp_exit_intents(
        [{
            "id": 2,
            "figi": "TREEUSDT",
            "side": "buy",
            "quantity": 10,
            "entry_price": 1.0,
            "created_at": created,
        }],
        {"TREEUSDT": 0.97},
        {
            "stop_loss_percent": 2,
            "take_profit_percent": 3,
            "min_hold_seconds": 120,
            "min_tp_move_bps": 50,
        },
        cost_kw={"broker_commission_rate": 0.0, "ndfl_rate": 0.0},
        now=now,
    )
    assert len(intents) == 1
    assert intents[0].reason == "stop_loss"
    assert intents[0].order_type == "MARKET"


def test_should_skip_take_profit_helpers():
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    pos = {
        "entry_price": 1.0,
        "created_at": now - timedelta(seconds=5),
    }
    assert "min_hold" in (should_skip_take_profit(
        pos, current_price=1.05, risk_params={"min_hold_seconds": 60, "min_tp_move_bps": 0}, now=now
    ) or "")
    assert should_skip_take_profit(
        pos, current_price=1.05, risk_params={"min_hold_seconds": 0, "min_tp_move_bps": 10}, now=now
    ) is None


def test_size_live_strategy_signal_buy_and_sell_filters():
    qty, err = RiskManager.size_live_strategy_signal(
        side="BUY",
        current_price=100.0,
        portfolio_value=10_000.0,
        free_funds=10_000.0,
        held_qty=0.0,
        risk_params={
            "max_position_percent": 10,
            "take_profit_percent": 3,
            "broker_commission": 0.0005,
            "exchange_fee": 0.0001,
            "slippage_bps": 0,
            "ndfl": 0.13,
        },
    )
    assert err is None and qty and qty > 0

    qty2, err2 = RiskManager.size_live_strategy_signal(
        side="SELL",
        current_price=100.0,
        portfolio_value=10_000.0,
        free_funds=10_000.0,
        held_qty=0.0,
        risk_params={"allow_short": False},
        strategy_params={"sell_only_if_has_asset": True},
    )
    assert qty2 is None
    assert err2 == "SELL_DOWNGRADED_NO_ASSET"
