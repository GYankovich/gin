"""Tests for strategy interval resolution (M1/M5/M10/…)."""
from __future__ import annotations

from app.modules.robots.trading.intervals import (
    MOEX_ISS_CANDLE_INTERVAL_CODES,
    resolve_candle_interval_roles,
    resolve_strategy_interval,
)


def test_resolve_m5_variants():
    for raw in ("CANDLE_INTERVAL_5_MIN", "M5", "I5", "5m"):
        r = resolve_strategy_interval(raw)
        assert r.code_num == 5
        assert r.cache_label == "M5"
        assert r.moex_interval_code == 5
        assert not r.supports_moex_iss


def test_interval_roles_m5_execution_moex_10m():
    roles = resolve_candle_interval_roles({"interval": "CANDLE_INTERVAL_5_MIN"})
    assert roles.execution.code_num == 5
    assert roles.moex_history.code_num == 10
    assert roles.moex_history.supports_moex_iss


def test_interval_roles_explicit_moex():
    roles = resolve_candle_interval_roles({
        "interval": "CANDLE_INTERVAL_5_MIN",
        "moex_analysis_interval": "CANDLE_INTERVAL_60_MIN",
    })
    assert roles.execution.code_num == 5
    assert roles.moex_history.code_num == 60


def test_resolve_m1_m10_h1_d1():
    r1 = resolve_strategy_interval("CANDLE_INTERVAL_1_MIN")
    assert r1.code_num == 1 and r1.cache_label == "I1" and r1.shared_canonical == "1m"

    r10 = resolve_strategy_interval("M10")
    assert r10.code_num == 10 and r10.shared_canonical == "10m"

    rh = resolve_strategy_interval("CANDLE_INTERVAL_HOUR")
    assert rh.code_num == 60 and rh.shared_canonical == "1h"

    rd = resolve_strategy_interval("CANDLE_INTERVAL_DAY")
    assert rd.code_num == 24 and rd.cache_label == "D1" and rd.shared_canonical == "1d"


def test_normalize_interval_by_broker():
    from app.modules.robots.trading.intervals import (
        normalize_bybit_interval,
        normalize_interval,
        normalize_tinvest_interval,
    )

    assert normalize_tinvest_interval("CANDLE_INTERVAL_5_MIN") == "CANDLE_INTERVAL_5_MIN"
    assert normalize_tinvest_interval("5m") == "CANDLE_INTERVAL_5_MIN"
    assert normalize_bybit_interval("5m") == "5m"
    assert normalize_bybit_interval("CANDLE_INTERVAL_5_MIN") == "5m"
    assert normalize_bybit_interval("CANDLE_INTERVAL_10_MIN") == "15m"
    assert normalize_interval("CANDLE_INTERVAL_5_MIN", "tinvest") == "CANDLE_INTERVAL_5_MIN"
    assert normalize_interval("CANDLE_INTERVAL_5_MIN", "bybit") == "5m"
    assert normalize_interval("5m", "bybit") == "5m"


def test_unsupported_moex_intervals():
    r15 = resolve_strategy_interval("CANDLE_INTERVAL_15_MIN")
    assert r15.code_num == 15
    assert r15.moex_interval_code == 15
    assert 15 not in MOEX_ISS_CANDLE_INTERVAL_CODES
    assert not r15.supports_moex_iss
    roles = resolve_candle_interval_roles({"moex_analysis_interval": "CANDLE_INTERVAL_15_MIN"})
    assert roles.moex_history.code_num == 10
