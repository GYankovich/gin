"""Funding charge step in BacktestTradingSession (R7.3)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.modules.robots.trading.brokers.sim_backtest import SimBacktestBrokerFacade
from app.modules.robots.trading.session_backtest import (
    BacktestTradingSession,
    _funding_events_in_window,
)


def test_funding_events_in_window():
    events = [
        {"funding_time": datetime(2024, 6, 1, 8, 0, tzinfo=timezone.utc), "funding_rate": 0.0001},
        {"funding_time": datetime(2024, 6, 1, 16, 0, tzinfo=timezone.utc), "funding_rate": 0.0002},
    ]
    due = _funding_events_in_window(
        "2024-06-01T07:00:00+00:00",
        "2024-06-01T09:00:00+00:00",
        events,
    )
    assert len(due) == 1
    assert due[0]["funding_rate"] == 0.0001


def test_apply_funding_charge_long_pays():
    broker = SimBacktestBrokerFacade(
        initial_capital=10_000.0,
        candles_by_figi={},
        ndfl_rate=0.0,
    )
    broker.holdings["BTCUSDT"] = {"qty": 1.0, "avg_price": 100.0}
    broker.set_last_price("BTCUSDT", 100.0)
    cash_before = broker.cash
    adj = broker.apply_funding_charge("BTCUSDT", 0.0001, bar_time="2024-06-01T08:00:00+00:00")
    assert adj == -0.01
    assert broker.cash == cash_before - 0.01
    assert len(broker.funding_log) == 1


def test_apply_funding_charge_skips_flat():
    broker = SimBacktestBrokerFacade(initial_capital=10_000.0, candles_by_figi={}, ndfl_rate=0.0)
    assert broker.apply_funding_charge("BTCUSDT", 0.0001) == 0.0


def test_backtest_session_applies_funding_on_bar():
    broker = SimBacktestBrokerFacade(
        initial_capital=10_000.0,
        candles_by_figi={"BTCUSDT": []},
        ndfl_rate=0.0,
    )
    broker.holdings["BTCUSDT"] = {"qty": 1.0, "avg_price": 100.0}
    broker.set_last_price("BTCUSDT", 100.0)

    session = BacktestTradingSession(
        db=MagicMock(),
        schema="ganaly",
        robot_id=1,
        user_id=1,
        token_id=0,
        token="",
        config={
            "broker_type": "bybit",
            "costs": {"funding_rate_enabled": True},
            "bybit": {"instrument_category": "linear"},
            "strategy": "momentum_breakout",
            "strategy_params": {},
            "risk": {},
        },
        sim_broker=broker,
        allowed_figis_by_date={},
    )
    ft = datetime(2024, 6, 1, 8, 0, tzinfo=timezone.utc)
    session._funding_by_symbol = {
        "BTCUSDT": [{"funding_time": ft, "funding_rate": 0.0001}],
    }
    cash_before = broker.cash
    session._apply_funding_charges_for_bar("2024-06-01T09:00:00+00:00")
    assert broker.cash < cash_before
    assert len(broker.funding_log) == 1


def test_crypto_funding_disabled_for_spot():
    broker = SimBacktestBrokerFacade(initial_capital=10_000.0, candles_by_figi={}, ndfl_rate=0.0)
    session = BacktestTradingSession(
        db=MagicMock(),
        schema="ganaly",
        robot_id=1,
        user_id=1,
        token_id=0,
        token="",
        config={
            "broker_type": "bybit",
            "costs": {"funding_rate_enabled": True},
            "bybit": {"instrument_category": "spot"},
            "strategy": "momentum_breakout",
            "strategy_params": {},
            "risk": {},
        },
        sim_broker=broker,
        allowed_figis_by_date={},
    )
    assert session._crypto_funding_enabled() is False
