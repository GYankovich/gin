from __future__ import annotations

from app.modules.robots.live_ws import _build_ws_init_payload, _normalize_instruments


def test_normalize_instruments_bybit_prefers_allowed_symbols():
    cfg = {
        "broker_type": "bybit",
        "allowed_symbols": ["btcusdt", "ethusdt"],
    }
    assert _normalize_instruments(cfg) == ["BTCUSDT", "ETHUSDT"]


def test_normalize_instruments_tinvest_uses_allowed_figis():
    cfg = {
        "broker_type": "tinvest",
        "allowed_figis": ["bbg004730n88", " BBG00475K2X9 "],
    }
    assert _normalize_instruments(cfg) == ["BBG004730N88", "BBG00475K2X9"]


def test_build_ws_init_payload_contains_instruments_and_legacy_figis():
    payload = _build_ws_init_payload(7, "bybit", ["BTCUSDT"])
    assert payload["type"] == "init"
    assert payload["robot_id"] == 7
    assert payload["broker_type"] == "bybit"
    assert payload["instruments"] == ["BTCUSDT"]
    assert payload["figis"] == ["BTCUSDT"]

