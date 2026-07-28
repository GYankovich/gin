"""Live wiring smoke: ByBit API secret + perp positions (mainnet, leverage=1)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.robots.trading.brokers.bybit import ByBitBrokerFacade
from app.modules.robots.trading.brokers.factory import create_broker_facade
from app.modules.robots.trading.brokers.routing import (
    resolve_bybit_api_secret,
    resolve_bybit_instrument_category,
)
from app.modules.robots.trading.contracts import ExecutionMode
from app.modules.robots.trading.session import TradingSession


def test_resolve_bybit_api_secret_from_extra_data():
    assert resolve_bybit_api_secret(token_extra_data={"token_secret": "sec-1"}) == "sec-1"
    assert resolve_bybit_api_secret(api_secret="direct") == "direct"
    assert resolve_bybit_api_secret() is None


def test_resolve_bybit_instrument_category_from_config():
    assert resolve_bybit_instrument_category({"bybit": {"instrument_category": "linear"}}) == "linear"
    assert resolve_bybit_instrument_category({}) == "linear"


def test_create_broker_facade_bybit_passes_secret_to_http_client():
    broker = create_broker_facade(
        "bybit",
        "api-key",
        token_extra_data={"token_secret": "api-secret"},
        robot_config={"bybit": {"instrument_category": "linear", "leverage": 1}},
    )
    assert isinstance(broker, ByBitBrokerFacade)
    assert broker._http._signer is not None
    assert broker._instrument_category == "linear"


def test_trading_session_broker_uses_token_extra_data():
    cfg = {
        "broker_type": "bybit",
        "allowed_symbols": ["BTCUSDT"],
        "bybit": {"instrument_category": "linear", "leverage": 1},
        "signal_generation": {"strategy": "reversion_to_ma", "params": {"interval": "5m"}},
    }
    session = TradingSession(
        db=MagicMock(),
        schema="ganaly",
        robot_id=1,
        user_id=1,
        token_id=1,
        token="api-key",
        config=cfg,
        token_extra_data={"token_secret": "api-secret"},
        mode=ExecutionMode.LIVE,
    )
    broker = session.broker
    assert isinstance(broker, ByBitBrokerFacade)
    assert broker._http._signer is not None


def test_bybit_get_portfolio_merges_linear_positions():
    http = MagicMock()
    http.get_wallet_balance = AsyncMock(
        return_value={
            "result": {
                "list": [
                    {
                        "totalEquity": "10500",
                        "totalAvailableBalance": "8000",
                        "coin": [
                            {"coin": "USDT", "walletBalance": "8000"},
                            {"coin": "BTC", "walletBalance": "0.01"},
                        ],
                    }
                ]
            }
        }
    )
    http.get_positions = AsyncMock(
        return_value={
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "size": "0.05",
                        "avgPrice": "65000",
                        "markPrice": "66000",
                        "unrealisedPnl": "50",
                    },
                    {
                        "symbol": "ETHUSDT",
                        "side": "Sell",
                        "size": "1",
                        "avgPrice": "3000",
                        "markPrice": "2900",
                    },
                ]
            }
        }
    )
    http.get_asset_overview = AsyncMock(return_value={"result": {"list": []}})
    broker = ByBitBrokerFacade("key", api_secret="secret", http_client=http, ws_client=MagicMock())

    portfolio = asyncio.run(broker.get_portfolio(broker.make_account_id("UNIFIED")))

    figis = [p["figi"] for p in portfolio["positions"]]
    assert "USDT" in figis
    assert "BTCUSDT" in figis
    assert "ETHUSDT" in figis
    assert "BTC" not in figis
    btc = next(p for p in portfolio["positions"] if p["figi"] == "BTCUSDT")
    eth = next(p for p in portfolio["positions"] if p["figi"] == "ETHUSDT")
    assert btc["quantity"]["decimal"] == pytest.approx(0.05)
    assert btc["side"] == "Buy"
    assert eth["quantity"]["decimal"] == pytest.approx(-1.0)
    assert eth["side"] == "Sell"
    assert portfolio["free_funds"] == pytest.approx(8000.0)
    assert portfolio["total_amount_futures"]["decimal"] == pytest.approx(0.05 * 66000 + 1 * 2900)
