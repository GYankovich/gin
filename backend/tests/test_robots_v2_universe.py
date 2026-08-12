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
