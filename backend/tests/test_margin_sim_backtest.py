"""Margin and liquidation tests for SimBacktestBrokerFacade."""

from __future__ import annotations

import pytest

from app.modules.robots.trading.brokers.margin import liquidation_price_long
from app.modules.robots.trading.brokers.sim_backtest import SimBacktestBrokerFacade


def test_liquidation_price_long_10x():
    liq = liquidation_price_long(100.0, 10.0, 0.005)
    assert liq == pytest.approx(90.5)


def test_margin_buy_requires_initial_margin_not_full_notional():
    broker = SimBacktestBrokerFacade(
        initial_capital=10_000.0,
        candles_by_figi={},
        margin_enabled=True,
        leverage=10.0,
        maintenance_margin_rate=0.005,
    )
    broker.set_last_price("BTCUSDT", 50_000.0)
    import asyncio

    asyncio.run(
        broker.post_market_order(
            "BTCUSDT",
            quantity=1,
            direction="ORDER_DIRECTION_BUY",
            account_id="BACKTEST",
        )
    )
    # notional 50k, margin 5k + fee
    assert broker.cash < 5_500.0
    assert broker.cash > 4_000.0
    h = broker.holdings["BTCUSDT"]
    assert h["margin_locked"] == pytest.approx(5_000.0)


def test_liquidation_closes_position():
    broker = SimBacktestBrokerFacade(
        initial_capital=10_000.0,
        candles_by_figi={},
        margin_enabled=True,
        leverage=10.0,
        maintenance_margin_rate=0.005,
    )
    broker.set_last_price("BTCUSDT", 100.0)
    import asyncio

    asyncio.run(
        broker.post_market_order("BTCUSDT", 10, "ORDER_DIRECTION_BUY", "BACKTEST")
    )
    liq_px = liquidation_price_long(100.0, 10.0, 0.005)
    broker.set_last_price("BTCUSDT", liq_px - 0.01)
    events = broker.check_liquidations()
    assert len(events) == 1
    assert "BTCUSDT" not in broker.holdings or float(broker.holdings.get("BTCUSDT", {}).get("qty") or 0) <= 0
