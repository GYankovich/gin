from __future__ import annotations

from app.modules.robots.trading.pipeline.bybit_symbol_filter import (
    filter_backtest_universe_symbols,
    is_dated_bybit_contract,
)


def test_is_dated_bybit_contract_perpetuals():
    assert not is_dated_bybit_contract("BTCUSDT")
    assert not is_dated_bybit_contract("ETHUSDT")
    assert not is_dated_bybit_contract("SOLUSDT")


def test_is_dated_bybit_contract_quarterly():
    assert is_dated_bybit_contract("BTCUSDT-25SEP26")
    assert is_dated_bybit_contract("ETHUSDT-27MAR26")
    assert is_dated_bybit_contract("btcusdt-25sep26")


def test_filter_backtest_universe_symbols():
    raw = ["BTCUSDT", "ETHUSDT", "BTCUSDT-25SEP26", "ETHUSDT-27MAR26", "BTCUSDT"]
    assert filter_backtest_universe_symbols(raw) == ["BTCUSDT", "ETHUSDT"]
