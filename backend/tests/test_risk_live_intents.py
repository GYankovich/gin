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

from app.modules.robots.trading.risk.manager import RiskManager, should_skip_take_profit


def test_plan_sl_tp_exit_intents_take_profit():
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
        {"TREEUSDT": 0.97},  # -3% vs 2% SL
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


def test_plan_sl_tp_skips_soft_tp_below_min_move_bps():
    # TP% is tiny so price crosses TP while absolute move still < min_tp_move_bps.
    intents = RiskManager.plan_sl_tp_exit_intents(
        [{"id": 3, "figi": "TREEUSDT", "side": "buy", "quantity": 10, "entry_price": 1.0}],
        {"TREEUSDT": 1.0006},  # +6 bps
        {
            "stop_loss_percent": 2,
            "take_profit_percent": 0.05,
            "min_hold_seconds": 0,
            "min_tp_move_bps": 10,
        },
        cost_kw={"broker_commission_rate": 0.0, "ndfl_rate": 0.0},
    )
    assert intents == []


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
