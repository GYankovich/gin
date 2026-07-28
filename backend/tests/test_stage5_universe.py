"""Unit tests for Stage5 live universe = accepted today ∪ positions."""

from __future__ import annotations

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robots.trading.broker_position_sync import extract_account_position_meta
from app.modules.robots.trading.stage5_universe import (
    collect_open_position_symbols,
    merge_stage5_figis,
)


def test_merge_stage5_prefers_positions_then_accepted():
    merged = merge_stage5_figis(
        accepted_today=["AAAUSDT", "BBBUSDT", "XLMUSDT"],
        open_symbols=["XLMUSDT", "ETHUSDT"],
    )
    assert merged[0] == "XLMUSDT"
    assert merged[1] == "ETHUSDT"
    assert "AAAUSDT" in merged
    assert merged.count("XLMUSDT") == 1


def test_collect_open_skips_currency_via_meta():
    meta = extract_account_position_meta(
        [
            {
                "figi": "USDT",
                "ticker": "USDT",
                "instrument_type": "currency",
                "quantity": {"decimal": 100.0},
                "average_position_price": {"decimal": 1.0},
                "current_price": {"decimal": 1.0},
            },
            {
                "figi": "XLMUSDT",
                "ticker": "XLMUSDT",
                "instrument_type": "crypto_perpetual",
                "quantity": {"decimal": 52.0},
                "side": "Buy",
                "average_position_price": {"decimal": 0.19},
                "current_price": {"decimal": 0.20},
            },
        ]
    )
    syms = collect_open_position_symbols(
        open_positions=[],
        account_position_meta=meta,
    )
    assert syms == ["XLMUSDT"]
    assert "USDT" not in syms


def test_collect_open_includes_db_positions():
    syms = collect_open_position_symbols(
        open_positions=[{"figi": "BTCUSDT", "side": "buy", "quantity": 0.01}],
        account_position_meta={},
    )
    assert syms == ["BTCUSDT"]
