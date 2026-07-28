from __future__ import annotations

import pytest

from app.modules.robots.crypto_universe import (
    CryptoUniverseFilters,
    ScreeningRow,
    apply_basic_filters,
    apply_derivative_filters,
    apply_volatility_filters,
    resolve_crypto_universe_filters,
)
from app.modules.robots.crypto_universe_metrics import (
    compute_atr_percent,
    compute_rvol,
    passes_funding_range,
)


def test_resolve_crypto_universe_filters_extended_defaults():
    cfg = {
        "crypto_universe": {
            "min_volume_24h_usd": 50_000_000,
            "max_spread_bps": 15,
            "max_funding_rate": 0.0002,
            "min_open_interest_usd": 10_000_000,
            "min_rvol": 2.0,
        },
        "bybit": {"instrument_category": "linear"},
    }
    flt = resolve_crypto_universe_filters(cfg)
    assert flt.min_turnover_24h_usd == 50_000_000
    assert flt.max_spread_pct == pytest.approx(0.15)
    assert flt.max_funding_rate == pytest.approx(0.0002)
    assert flt.min_open_interest_usd == 10_000_000
    assert flt.min_rvol == 2.0
    assert flt.lookback_days == 20


def test_apply_basic_filters_volume_and_spread():
    filters = CryptoUniverseFilters(min_turnover_24h_usd=50_000_000, max_spread_pct=0.15)
    tickers = [
        {"symbol": "BTCUSDT", "turnover24h": 100_000_000, "lastPrice": 50000, "bid1Price": 49990, "ask1Price": 50010},
        {"symbol": "LOWUSDT", "turnover24h": 1_000_000, "lastPrice": 1, "bid1Price": 0.99, "ask1Price": 1.01},
        {"symbol": "WIDEUSDT", "turnover24h": 100_000_000, "lastPrice": 10, "bid1Price": 9.5, "ask1Price": 10.5},
    ]
    accepted, rejected = apply_basic_filters(tickers, filters=filters)
    assert [r.symbol for r in accepted] == ["BTCUSDT"]
    reasons = {r.symbol: r.reject_reason for r in rejected}
    assert reasons["LOWUSDT"] == "volume_below_min"
    assert reasons["WIDEUSDT"] == "spread_above_max"


def test_apply_basic_filters_skips_spread_on_daily_range_only():
    filters = CryptoUniverseFilters(
        min_turnover_24h_usd=0,
        max_spread_pct=0.15,
        min_last_price=0,
    )
    tickers = [
        {
            "symbol": "PEPEUSDT",
            "turnover24h": 100_000_000,
            "lastPrice": 0.0034,
            "dailyRangePercent": 12.13,
        },
    ]
    accepted, rejected = apply_basic_filters(tickers, filters=filters)
    assert rejected == []
    assert accepted[0].symbol == "PEPEUSDT"
    assert accepted[0].dailyRangePercent == pytest.approx(12.13)
    assert accepted[0].spreadPercent is None


def test_derivative_and_volatility_filters():
    filters = CryptoUniverseFilters(
        min_funding_rate=-0.0001,
        max_funding_rate=0.0002,
        min_open_interest_usd=10_000_000,
        min_lsr=0.5,
        max_lsr=1.5,
        min_rvol=2.0,
        min_atr_percent=1.5,
        max_atr_percent=10.0,
    )
    row = ScreeningRow(
        symbol="ETHUSDT",
        turnover24h=80_000_000,
        lastPrice=3000,
        spreadPercent=0.05,
        avg_funding_rate=0.0001,
        open_interest_usd=20_000_000,
        lsr=1.0,
        rvol=2.5,
        atr_percent=3.0,
    )
    assert apply_derivative_filters(row, filters=filters) is True
    assert apply_volatility_filters(row, filters=filters) is True

    hot = ScreeningRow(
        symbol="HOTUSDT",
        turnover24h=80_000_000,
        lastPrice=1,
        spreadPercent=0.05,
        avg_funding_rate=0.001,
        open_interest_usd=20_000_000,
        lsr=1.0,
        rvol=2.5,
        atr_percent=3.0,
    )
    assert apply_derivative_filters(hot, filters=filters) is False
    assert hot.reject_reason.startswith("funding_above_max")


def test_compute_rvol_and_atr():
    volumes = [100.0, 100.0, 100.0, 200.0]
    assert compute_rvol(volumes) == pytest.approx(2.0)
    highs = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
    lows = [9] * 15
    closes = [10 + i * 0.1 for i in range(15)]
    atr_pct = compute_atr_percent(highs, lows, closes, period=14)
    assert atr_pct is not None
    assert atr_pct > 0


def test_passes_funding_range():
    ok, _ = passes_funding_range(0.0001, min_rate=-0.0001, max_rate=0.0002)
    assert ok is True
    ok, reason = passes_funding_range(0.001, min_rate=-0.0001, max_rate=0.0002)
    assert ok is False
    assert "funding_above_max" in reason
