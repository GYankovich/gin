"""Broker routing (BRD-ARCH-04)."""

from __future__ import annotations

from app.modules.robots.trading.brokers.factory import create_broker_facade
from app.modules.robots.trading.brokers.routing import (
    filter_allowed_instruments,
    is_supported_live_broker,
    live_market_data_provider,
    normalize_broker_type,
)
from app.modules.robots.trading.brokers.bybit import ByBitBrokerFacade
from app.modules.robots.trading.brokers.tinvest import TInvestBrokerFacade


def test_normalize_broker_type():
    assert normalize_broker_type("TINVEST") == "tinvest"
    assert normalize_broker_type(None) == "tinvest"
    # dictionary TOKEN.TYPE.string_value (canonical)
    assert normalize_broker_type("tinvest") == "tinvest"
    assert normalize_broker_type("bybit") == "bybit"
    # legacy aliases
    assert normalize_broker_type("tinkoff") == "tinvest"


def test_filter_instruments_tinvest():
    figis, dropped = filter_allowed_instruments(
        "tinvest",
        ["BBG004730N88", "SBER", "RU000A0JX0J2"],
    )
    assert figis == ["BBG004730N88"]
    assert dropped == 2


def test_live_market_provider():
    assert live_market_data_provider("tinvest") == "tinvest"
    assert live_market_data_provider("bybit") == "bybit_market"
    assert live_market_data_provider("vtb") == "unknown"


def test_create_broker_facade_tinvest():
    b = create_broker_facade("tinvest", "token-x")
    assert isinstance(b, TInvestBrokerFacade)


def test_is_supported_live_broker():
    assert is_supported_live_broker("tinvest")
    assert is_supported_live_broker("bybit")
    assert not is_supported_live_broker("bitby")
    assert not is_supported_live_broker("vtb")


def test_create_broker_facade_bybit():
    b = create_broker_facade("bybit", "token-y")
    assert isinstance(b, ByBitBrokerFacade)
