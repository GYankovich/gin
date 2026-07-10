"""Bybit config merge and API normalization."""

from __future__ import annotations

from app.modules.robots.service import RobotService


def test_merge_trading_robot_config_bybit_preserves_universe_mode():
    svc = RobotService()
    incoming = {
        "config_version": 3,
        "schema_profile": "type2_bybit",
        "broker_type": "bybit",
        "universe_mode": "fixed",
        "allowed_symbols": ["BTCUSDT"],
        "bybit": {"instrument_category": "linear", "leverage": 1},
        "signal_generation": {"strategy": "reversion_to_ma", "params": {"interval": "1h"}},
        "risk": {"max_position_percent": 10.0, "risk_per_trade_pct": 2.0},
        "costs": {"maker_fee_rate": 0.0002, "taker_fee_rate": 0.00055},
    }
    cfg = svc._merge_trading_robot_config(incoming)
    assert cfg["broker_type"] == "bybit"
    assert cfg["universe_mode"] == "fixed"
    assert cfg["allowed_symbols"] == ["BTCUSDT"]
    assert "dms_pipeline" not in str(cfg.get("pipeline", {}))


def test_merge_trading_robot_config_bybit_auto_universe_mode():
    svc = RobotService()
    incoming = {
        "config_version": 3,
        "schema_profile": "type2_bybit",
        "broker_type": "bybit",
        "market_profile": "crypto",
        "universe_mode": "auto",
        "signal_generation": {
            "strategy": "momentum_breakout",
            "params": {"interval": "1m", "candle_days": 12},
            "data_source": "bybit",
        },
        "crypto_universe": {"enabled": True},
        "bybit": {"instrument_category": "linear", "leverage": 1},
        "risk": {"max_position_percent": 20.0},
        "costs": {"maker_fee_rate": 0.0001, "taker_fee_rate": 0.0006},
    }
    cfg = svc._merge_trading_robot_config(incoming)
    assert cfg["universe_mode"] == "auto"


def test_merge_config_v2_does_not_corrupt_crypto_universe_mode():
    from app.modules.robots.config.migration import merge_config_v2

    svc = RobotService()
    base = svc._default_trading_robot_config()
    incoming = {
        "broker_type": "bybit",
        "schema_profile": "type2_bybit",
        "universe_mode": "auto",
        "signal_generation": {"strategy": "reversion_to_ma", "data_source": "bybit", "params": {}},
        "crypto_universe": {"enabled": True},
    }
    merged = merge_config_v2(base, incoming)
    assert merged.get("universe_mode") == "auto"


def test_normalize_trading_robot_config_for_api_preserves_bybit():
    raw = {
        "broker_type": "bybit",
        "schema_profile": "type2_bybit",
        "universe_mode": "fixed",
        "allowed_symbols": ["BTCUSDT"],
        "signal_generation": {"strategy": "reversion_to_ma", "data_source": "bybit"},
    }
    out = RobotService._normalize_trading_robot_config_for_api(raw)
    assert out["broker_type"] == "bybit"
    assert out["allowed_symbols"] == ["BTCUSDT"]
    assert out.get("universe_mode") == "fixed"
