import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.universe import presets


def test_moex_high_liquidity_preset_maps_to_dms_filters():
    filters = presets.resolve_moex_dms_filters(preset="high_liquidity", custom_filters=None)
    types = {str(f["type"]) for f in filters}
    assert "volume" in types
    assert "spread" in types
    assert "min_avg_volume" in types


def test_v4_volume_filter_maps_to_dms():
    mapped = presets.map_v4_filter_to_dms({"type": "volume", "op": ">", "value": 10_000_000, "period": "session"})
    assert mapped == {"type": "volume", "min": 10_000_000.0}


def test_moex_price_bounds_from_custom_filters():
    lo, hi = presets.moex_price_bounds(
        None,
        [{"type": "price", "op": ">", "value": 10}, {"type": "price", "op": "<", "value": 500}],
    )
    assert lo == 10.0
    assert hi == 500.0


def test_crypto_high_liquidity_preset():
    cfg = presets.resolve_crypto_filters(preset="high_liquidity", custom_filters=None)
    assert cfg["min_volume_24h_usd"] == 50_000_000
    assert cfg["max_spread_pct"] == 0.1


def test_filters_without_trading_status_keeps_other_gates():
    from app.modules.robots_v2.universe.service import (
        _filters_without_trading_status,
        _has_trading_status_filter,
    )

    filters = [
        {"type": "security_status", "eq": "A"},
        {"type": "trading_status", "eq": "T"},
        {"type": "volume", "min": 10_000_000},
    ]
    assert _has_trading_status_filter(filters) is True
    relaxed = _filters_without_trading_status(filters)
    assert _has_trading_status_filter(relaxed) is False
    assert {"type": "security_status", "eq": "A"} in relaxed
    assert {"type": "volume", "min": 10_000_000} in relaxed


def test_filter_tqbr_candidate_rows_falls_back_when_board_is_n():
    from app.modules.robots.universe import filter_tqbr_candidate_rows

    overnight = [
        {"ticker": "SBER", "security_status": "A", "trading_status": "N"},
        {"ticker": "GAZP", "security_status": "A", "trading_status": "N"},
        {"ticker": "BAD", "security_status": "B", "trading_status": "N"},
    ]
    out = filter_tqbr_candidate_rows(overnight)
    assert {r["ticker"] for r in out} == {"SBER", "GAZP"}

    session_open = [
        {"ticker": "SBER", "security_status": "A", "trading_status": "T"},
        {"ticker": "GAZP", "security_status": "A", "trading_status": "N"},
    ]
    out2 = filter_tqbr_candidate_rows(session_open)
    assert [r["ticker"] for r in out2] == ["SBER"]
