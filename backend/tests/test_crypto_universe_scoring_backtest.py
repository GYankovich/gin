from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from app.modules.robots.config.profiles import dump_robot_config, validate_robot_config
from app.modules.robots.crypto_universe import (
    CryptoUniverseFilters,
    apply_basic_filters,
    resolve_crypto_universe_filters,
)
from app.modules.robots.trading.pipeline.crypto_universe_scoring import (
    run_history_crypto_universe_scoring,
)
from app.modules.robots.universe import (
    UNIVERSE_MODE_AUTO,
    UNIVERSE_MODE_FIXED,
    normalize_crypto_universe_mode,
    resolve_crypto_symbols,
)


def test_normalize_crypto_universe_mode_fixed_from_symbols():
    cfg = {"allowed_symbols": ["BTCUSDT"]}
    assert normalize_crypto_universe_mode(cfg) == UNIVERSE_MODE_FIXED


def test_normalize_crypto_universe_mode_auto_when_enabled_without_symbols():
    cfg = {"crypto_universe": {"enabled": True}}
    assert normalize_crypto_universe_mode(cfg) == UNIVERSE_MODE_AUTO


def test_normalize_crypto_universe_mode_explicit():
    cfg = {"universe_mode": "auto", "crypto_universe": {"enabled": True}}
    assert normalize_crypto_universe_mode(cfg) == UNIVERSE_MODE_AUTO


def test_resolve_crypto_symbols_normalizes():
    assert resolve_crypto_symbols({"instruments": ["btcusdt", "ethusdt"]}) == ["BTCUSDT", "ETHUSDT"]


def test_resolve_crypto_universe_filters_zero_min_last_price():
    flt = resolve_crypto_universe_filters({"crypto_universe": {"min_last_price": 0}})
    assert flt.min_last_price == 0


def test_apply_basic_filters_skips_price_when_min_last_price_zero():
    flt = CryptoUniverseFilters(
        min_turnover_24h_usd=0,
        max_spread_pct=999,
        min_last_price=0,
    )
    tickers = [
        {
            "symbol": "LOWUSDT",
            "turnover24h": "100000000",
            "lastPrice": "0.0035",
            "bid1Price": "0.0035",
            "ask1Price": "0.00351",
        }
    ]
    accepted, rejected = apply_basic_filters(tickers, filters=flt)
    assert rejected == []
    assert [r.symbol for r in accepted] == ["LOWUSDT"]


def test_resolve_crypto_universe_filters_maps_bps_and_volume():
    cfg = {
        "crypto_universe": {
            "min_volume_24h_usd": 10_000_000,
            "max_spread_bps": 20,
        },
        "bybit": {"instrument_category": "linear"},
    }
    flt = resolve_crypto_universe_filters(cfg)
    assert flt.min_turnover_24h_usd == 10_000_000
    assert flt.max_spread_pct == pytest.approx(0.2)
    assert flt.category == "linear"


def test_validate_type2_bybit_auto_mode():
    model = validate_robot_config(
        robot_type=2,
        raw={
            "broker_type": "bybit",
            "universe_mode": "auto",
            "crypto_universe": {"enabled": True, "min_volume_24h_usd": 1_000_000},
            "signal_generation": {
                "strategy": "reversion_to_ma",
                "params": {"interval": "5m"},
                "data_source": "bybit",
            },
        },
        broker_type="bybit",
    )
    dumped = dump_robot_config(model)
    assert dumped["universe_mode"] == "auto"


def test_validate_type2_bybit_auto_requires_enabled():
    with pytest.raises(Exception):
        validate_robot_config(
            robot_type=2,
            raw={
                "broker_type": "bybit",
                "universe_mode": "auto",
                "crypto_universe": {"enabled": False},
            },
            broker_type="bybit",
        )


def test_run_history_crypto_universe_scoring_uses_cache(monkeypatch):
    class _DB:
        def execute(self, stmt, params):
            sql = str(stmt)
            if "crypto_universe_daily" in sql:
                return SimpleNamespace(
                    fetchall=lambda: [(date(2024, 1, 2), "BTCUSDT"), (date(2024, 1, 2), "ETHUSDT")]
                )
            return SimpleNamespace(fetchall=lambda: [])

    monkeypatch.setattr(
        "app.modules.robots.trading.pipeline.crypto_universe_scoring._score_symbols_for_trade_date",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("historical score should not run")),
    )

    result = asyncio.run(
        run_history_crypto_universe_scoring(
            db=_DB(),
            trade_dates=[date(2024, 1, 2)],
            config={"broker_type": "bybit", "universe_mode": "auto"},
            user_id=1,
            robot_id=7,
            run_id=99,
            is_cancelled=lambda: False,
        )
    )
    assert result.selected_tickers == ["BTCUSDT", "ETHUSDT"]
    assert result.allowed_figis_by_date["2024-01-02"] == ["BTCUSDT", "ETHUSDT"]


def test_run_history_crypto_universe_scoring_per_day_historical(monkeypatch):
    class _DB:
        def execute(self, stmt, params):
            return SimpleNamespace(fetchall=lambda: [])

    calls: list[date] = []

    def _fake_score(db, *, trade_date, config, candidate_pool):
        calls.append(trade_date)
        if trade_date == date(2024, 1, 2):
            return ["BTCUSDT"], [{"stage": "crypto_universe", "ticker": "BTCUSDT", "result": "ACCEPT"}], 120
        return ["ETHUSDT"], [{"stage": "crypto_universe", "ticker": "ETHUSDT", "result": "ACCEPT"}], 120

    monkeypatch.setattr(
        "app.modules.robots.trading.pipeline.crypto_universe_scoring._score_symbols_for_trade_date",
        _fake_score,
    )

    result = asyncio.run(
        run_history_crypto_universe_scoring(
            db=_DB(),
            trade_dates=[date(2024, 1, 2), date(2024, 1, 3)],
            config={"broker_type": "bybit", "universe_mode": "auto"},
            user_id=1,
            robot_id=None,
            run_id=99,
            is_cancelled=lambda: False,
        )
    )
    assert calls == [date(2024, 1, 2), date(2024, 1, 3)]
    assert result.allowed_figis_by_date["2024-01-02"] == ["BTCUSDT"]
    assert result.allowed_figis_by_date["2024-01-03"] == ["ETHUSDT"]
