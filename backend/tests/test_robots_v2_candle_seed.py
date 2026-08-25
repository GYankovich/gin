"""Unit tests for robots v2 candle seed helpers."""

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.config.v4_schema import TradingRobotConfigV4
from app.modules.robots_v2.engine.candle_seed import (
    _row_to_candle,
    lookback_days_for_warmup,
    warmup_bars_needed,
)


def _cfg(**kwargs):
    base = {
        "configVersion": 4,
        "core": {
            "goal": "aggressive",
            "instrumentType": "stock",
            "mode": "paper",
            "schedule": {
                "weekdays": [True, True, True, True, True, False, False],
                "timeFrom": "10:00",
                "timeTo": "18:40",
                "pollInterval": "1m",
            },
        },
        "strategy": {
            "archetype": "momentum",
            "timeframe": "1h",
            "params": {"maPeriod": 50, "volumeMultiplier": 2.0, "breakoutLookback": 20},
        },
        "universe": {"mode": "fixed", "fixedList": ["SBER"], "maxAssets": 5},
        "risk": {
            "capital": 10000,
            "maxPositionSharePct": 10,
            "stopLossPct": 2,
            "takeProfitPct": 4,
            "maxDailyLoss": 1000,
            "maxConcurrentPositions": 3,
            "brokerCommissionPct": 0.05,
            "taxPct": 13,
        },
    }
    base.update(kwargs)
    return TradingRobotConfigV4.model_validate(base)


def test_warmup_bars_momentum_70():
    assert warmup_bars_needed(_cfg()) == 70


def test_lookback_days_covers_1h_warmup():
    days = lookback_days_for_warmup(timeframe="1h", need_bars=70)
    assert days >= 20


def test_row_to_candle_parses_tinvest_units_nano():
    raw = {
        "time": "2024-01-01T10:00:00+00:00",
        "open": {"units": 100, "nano": 0},
        "high": {"units": 110, "nano": 0},
        "low": {"units": 95, "nano": 0},
        "close": {"units": 105, "nano": 0},
        "volume": 1000,
    }
    c = _row_to_candle(raw, tf="1h", ticker="GAZP")
    assert c is not None
    assert c.close == 105.0
    assert c.secid == "GAZP"


def test_looks_like_figi():
    from app.modules.robots_v2.engine.broker_factory import _looks_like_figi

    assert _looks_like_figi("BBG004730N88")
    assert not _looks_like_figi("GAZP")
    assert not _looks_like_figi("")


def test_instrument_map_prefers_figi_over_ticker_placeholder():
    """Universe often seeds ticker→ticker; real FIGI must overwrite."""
    instrument_map = {"GAZP": "GAZP", "SBER": "SBER"}
    resolved = {"GAZP": "BBG004730N88", "SBER": "BBG004730N88"}
    for tk, iid in resolved.items():
        prev = instrument_map.get(tk)
        if not prev or prev == tk or iid != tk:
            instrument_map[tk] = iid
    assert instrument_map["GAZP"].startswith("BBG")
    assert instrument_map["SBER"].startswith("BBG")
