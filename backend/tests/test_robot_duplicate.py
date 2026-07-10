"""Tests for robot duplicate config builder (R8.4)."""

from __future__ import annotations

import pytest

from app.modules.robots.config.duplicate import (
    build_duplicated_config,
    resolve_schedule_from_source,
    validate_duplicate_sections,
)


def test_validate_duplicate_sections_rejects_unknown():
    with pytest.raises(ValueError, match="Invalid copy_sections"):
        validate_duplicate_sections(["strategy"], [])


def test_build_duplicated_config_same_broker_resets_universe():
    source = {
        "broker_type": "tinvest",
        "strategy": "grain_seed",
        "strategy_params": {"interval": "CANDLE_INTERVAL_5_MIN"},
        "risk": {"stop_loss_percent": 2.0, "max_position_percent": 10.0},
        "costs": {"broker_commission_rate": 0.0005, "ndfl_rate": 0.13},
        "allowed_figis": ["BBG004730N88"],
        "candidate_pool": {"tickers": ["SBER"], "as_of": "2026-01-01"},
        "universe_mode": "dms_pipeline",
    }
    cfg = build_duplicated_config(
        robot_type=2,
        source_config=source,
        target_broker="tinvest",
    )
    assert cfg.get("broker_type") == "tinvest"
    assert cfg.get("strategy") == "grain_seed"
    assert cfg.get("allowed_figis") == []
    assert "candidate_pool" not in cfg


def test_build_duplicated_config_tinvest_to_bybit_changes_profile():
    source = {
        "broker_type": "tinvest",
        "strategy": "reversion_to_ma",
        "strategy_params": {"interval": "CANDLE_INTERVAL_5_MIN", "rsi_period": 14},
        "risk": {
            "stop_loss_percent": 2.5,
            "take_profit_percent": 4.0,
            "max_position_percent": 8.0,
            "max_position_rub": 100_000,
            "max_daily_loss": 5_000,
        },
        "costs": {"broker_commission_rate": 0.0005, "ndfl_rate": 0.13},
        "allowed_figis": ["BBG004730N88"],
    }
    cfg = build_duplicated_config(
        robot_type=2,
        source_config=source,
        target_broker="bybit",
    )
    assert cfg.get("schema_profile") == "type2_bybit"
    assert cfg.get("broker_type") == "bybit"
    assert cfg.get("allowed_symbols") == []
    assert not cfg.get("allowed_figis")
    assert cfg.get("risk", {}).get("max_position_percent") == 8.0
    assert cfg.get("risk", {}).get("max_daily_loss") == 5000.0
    sg = cfg.get("signal_generation") or {}
    assert sg.get("strategy") == "reversion_to_ma"


def test_resolve_schedule_from_source_copies_schedule():
    poll_h, start, end, weekdays = resolve_schedule_from_source(
        {"risk": {"trading_hours_start": "09:30 MSK", "trading_hours_end": "18:00 MSK", "allowed_weekdays": 31}},
        {"interval_seconds": 600, "start_time": "10:00:00+03:00", "end_time": "19:00:00+03:00", "weekdays": 31},
        copy_schedule=True,
    )
    assert poll_h == pytest.approx(10 / 60)
    assert start == "09:30"
    assert end == "18:00"
    assert weekdays == 31


def test_build_duplicated_config_type1_bybit():
    cfg = build_duplicated_config(
        robot_type=1,
        source_config={"broker_type": "tinvest"},
        target_broker="bybit",
    )
    assert cfg.get("schema_profile") == "type1_bybit"
    assert cfg.get("bybit", {}).get("testnet") is False
