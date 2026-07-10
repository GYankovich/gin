"""Tests for backend config profile registry (R2.1)."""

from __future__ import annotations

import pytest

from app.modules.robots.config.profiles import (
    PROFILE_REGISTRY,
    dump_robot_config,
    export_config_schema,
    resolve_schema_profile,
    validate_robot_config,
)


def test_profile_registry_contains_type2_tinvest():
    assert "type2_tinvest" in PROFILE_REGISTRY


def test_profile_registry_contains_type1_tinvest_and_bybit():
    assert "type1_tinvest" in PROFILE_REGISTRY
    assert "type1_bybit" in PROFILE_REGISTRY


def test_profile_registry_contains_type2_bybit():
    assert "type2_bybit" in PROFILE_REGISTRY


def test_resolve_schema_profile_type2_tinvest():
    profile = resolve_schema_profile(
        robot_type=2,
        raw={"broker_type": "tinvest"},
        broker_type=None,
    )
    assert profile == "type2_tinvest"


def test_resolve_schema_profile_type1_bybit():
    profile = resolve_schema_profile(
        robot_type=1,
        raw={"broker_type": "bybit"},
        broker_type=None,
    )
    assert profile == "type1_bybit"


def test_resolve_schema_profile_type2_bybit():
    profile = resolve_schema_profile(
        robot_type=2,
        raw={"broker_type": "bybit"},
        broker_type=None,
    )
    assert profile == "type2_bybit"


def test_validate_robot_config_type1_bybit():
    model = validate_robot_config(
        robot_type=1,
        raw={"bybit": {"testnet": False, "account_type": "UNIFIED"}},
        broker_type="bybit",
    )
    dumped = dump_robot_config(model)
    assert dumped["schema_profile"] == "type1_bybit"
    assert dumped["broker_type"] == "bybit"
    assert dumped["bybit"]["testnet"] is False


def test_validate_robot_config_type2_tinvest_normalizes_to_v3():
    model = validate_robot_config(
        robot_type=2,
        raw={
            "strategy": "momentum_breakout",
            "universe_mode": "dms_pipeline",
            "broker_type": "tinvest",
            "risk": {"stop_loss_percent": 2.0},
        },
    )
    dumped = dump_robot_config(model)
    assert dumped["config_version"] == 3
    assert dumped["schema_profile"] == "type2_tinvest"
    assert dumped["broker_type"] == "tinvest"
    assert dumped["signal_generation"]["strategy"] == "momentum_breakout"


def test_validate_robot_config_type2_bybit_preserves_zero_min_last_price():
    model = validate_robot_config(
        robot_type=2,
        raw={
            "broker_type": "bybit",
            "crypto_universe": {"enabled": True, "min_last_price": 0},
            "signal_generation": {
                "strategy": "reversion_to_ma",
                "params": {"interval": "5m"},
                "data_source": "bybit",
            },
        },
        broker_type="bybit",
    )
    dumped = dump_robot_config(model)
    assert dumped["crypto_universe"]["min_last_price"] == 0


def test_validate_robot_config_type2_bybit():
    model = validate_robot_config(
        robot_type=2,
        raw={
            "broker_type": "bybit",
            "instruments": ["btcusdt", "ethusdt"],
            "signal_generation": {
                "strategy": "reversion_to_ma",
                "params": {"interval": "5m", "ma_period": 20},
                "data_source": "bybit",
            },
            "costs": {"funding_rate_enabled": False},
        },
        broker_type="bybit",
    )
    dumped = dump_robot_config(model)
    assert dumped["schema_profile"] == "type2_bybit"
    assert dumped["broker_type"] == "bybit"
    assert dumped["instrument_id_type"] == "symbol"
    assert dumped["instruments"] == ["BTCUSDT", "ETHUSDT"]
    assert dumped["costs"]["funding_rate_enabled"] is False


def test_export_config_schema_type2_tinvest():
    schema = export_config_schema("type2_tinvest")
    assert isinstance(schema, dict)
    assert schema.get("title") == "Type2TinvestConfig"
    props = schema.get("properties") or {}
    assert "risk" in props
    assert "costs" in props
    assert "historical_screening" in props


def test_export_config_schema_type1_bybit():
    schema = export_config_schema("type1_bybit")
    assert isinstance(schema, dict)
    assert schema.get("title") == "Type1BybitConfig"
    props = schema.get("properties") or {}
    assert "bybit" in props


def test_export_config_schema_type2_bybit():
    schema = export_config_schema("type2_bybit")
    assert isinstance(schema, dict)
    assert schema.get("title") == "Type2BybitConfig"
    props = schema.get("properties") or {}
    assert "bybit" in props
    assert "crypto_universe" in props
    assert "allowed_symbols" in props


def test_export_config_schema_unknown_profile_raises():
    with pytest.raises(KeyError):
        export_config_schema("type2_unknown")


def test_dump_preserves_falsy_flags():
    model = validate_robot_config(
        robot_type=2,
        raw={
            "broker_type": "tinvest",
            "strategy": "momentum_breakout",
            "strategy_params": {
                "interval": "CANDLE_INTERVAL_10_MIN",
                "allow_entry_all_day": False,
                "sell_only_if_has_asset": False,
            },
            "risk": {
                "max_daily_loss": 0.0,
                "allowed_weekdays": 0,
                "trading_hours_start": "10:00 MSK",
                "trading_hours_end": "18:45 MSK",
            },
            "costs": {
                "broker_commission_rate": 0.0,
                "ndfl_rate": 0.0,
            },
        },
    )
    dumped = dump_robot_config(model)
    assert dumped["strategy_params"]["allow_entry_all_day"] is False
    assert dumped["strategy_params"]["sell_only_if_has_asset"] is False
    assert float(dumped["risk"]["max_daily_loss"]) == 0.0
    assert int(dumped["risk"]["allowed_weekdays"]) == 0
    assert float(dumped["costs"]["broker_commission_rate"]) == 0.0
    assert float(dumped["costs"]["ndfl_rate"]) == 0.0
