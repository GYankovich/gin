"""Тесты миграции config v1 → v2 (П1/П2/П3)."""
from __future__ import annotations

from app.modules.robots.config.migration import (
    CONFIG_VERSION_V3,
    ensure_config_v2,
    migrate_v2_to_v3,
    migrate_legacy_to_v2,
    merge_config_v2,
    resolve_schema_profile_v3,
)
from app.modules.robots.config.v2_schema import CONFIG_VERSION_V2
from app.modules.robots import schemas


def test_migrate_dms_pipeline_splits_atr():
    legacy = {
        "strategy": "momentum_breakout",
        "universe_mode": "dms_pipeline",
        "universe_refresh_minutes": 45,
        "strategy_params": {"interval": "CANDLE_INTERVAL_5_MIN", "candle_days": 14},
        "pipeline": {
            "mode": "ALL",
            "filters": [
                {"type": "volume", "min": 1000},
                {"type": "atr", "min_percent": 2.0, "period": 14},
            ],
        },
        "risk": {"stop_loss_percent": 2},
        "costs": {"broker_commission_rate": 0.0005},
    }
    out = migrate_legacy_to_v2(legacy)
    assert out["config_version"] == CONFIG_VERSION_V2
    assert out["historical_screening"]["enabled"] is True
    assert any(f.get("type") == "atr" for f in out["historical_screening"]["filters"])
    assert all(f.get("type") != "atr" for f in out["paper_selection"]["filters"])
    assert out["paper_selection"]["refresh"]["every_minutes"] == 45
    assert out["signal_generation"]["strategy"] == "momentum_breakout"
    assert out["strategy_params"]["interval"] == "CANDLE_INTERVAL_5_MIN"
    assert out["universe_mode"] in ("tqbr_scan", "dms_pipeline")


def test_migrate_fixed_skips_historical():
    out = migrate_legacy_to_v2({
        "universe_mode": "fixed",
        "fixed_tickers": ["SBER", "GAZP"],
        "pipeline": {"mode": "ALL", "filters": []},
        "strategy": "grain_seed",
        "strategy_params": {"ma_fast_period": 5, "ma_slow_period": 20},
    })
    assert out["historical_screening"]["enabled"] is False
    assert out["paper_selection"]["input"] == "fixed"
    assert out["universe_mode"] == "fixed"


def test_ensure_config_v2_idempotent():
    raw = migrate_legacy_to_v2({"universe_mode": "tqbr_scan", "pipeline": {"filters": []}})
    twice = ensure_config_v2(raw)
    assert twice["config_version"] == CONFIG_VERSION_V2
    assert "historical_screening" in twice


def test_grain_seed_config_validates_v2():
    cfg = schemas.GrainSeedConfig.model_validate(
        {"strategy": "momentum_breakout", "universe_mode": "dms_pipeline"}
    )
    assert cfg.config_version == CONFIG_VERSION_V2
    assert cfg.historical_screening is not None
    assert cfg.paper_selection is not None
    assert cfg.signal_generation is not None


def test_merge_config_v2_patches_paper_refresh():
    base = migrate_legacy_to_v2({"universe_mode": "dms_pipeline", "pipeline": {"filters": []}})
    merged = merge_config_v2(
        base,
        {"paper_selection": {"refresh": {"every_minutes": 15}}},
    )
    assert merged["paper_selection"]["refresh"]["every_minutes"] == 15
    assert merged["universe_refresh_minutes"] == 15


def test_migrate_dms_pipeline_without_atr_gets_default_p1():
    out = migrate_legacy_to_v2({
        "universe_mode": "dms_pipeline",
        "pipeline": {
            "mode": "ALL",
            "filters": [{"type": "volume", "min": 1_000_000}],
        },
        "strategy": "grain_seed",
        "strategy_params": {"interval": "CANDLE_INTERVAL_5_MIN"},
    })
    assert out["historical_screening"]["enabled"] is True
    assert any(f.get("type") == "atr" for f in out["historical_screening"]["filters"])
    assert out["paper_selection"]["input"] == "candidate_pool"
    assert out["universe_mode"] == "tqbr_scan"


def test_repair_v2_filter_split_from_pipeline_only():
    from app.modules.robots.config.migration import repair_v2_filter_split

    raw = {
        "config_version": 2,
        "historical_screening": {"enabled": True, "filters": []},
        "paper_selection": {"enabled": True, "filters": []},
        "signal_generation": {"strategy": "grain_seed", "params": {}},
        "pipeline": {
            "filters": [
                {"type": "atr", "min_percent": 2.0},
                {"type": "volume", "min": 1000},
            ],
        },
    }
    repaired = repair_v2_filter_split(raw)
    assert any(f.get("type") == "atr" for f in repaired["historical_screening"]["filters"])
    assert any(f.get("type") == "volume" for f in repaired["paper_selection"]["filters"])


def test_resolve_schema_profile_v3_type2_tinvest():
    profile = resolve_schema_profile_v3(
        robot_type=2,
        config={"broker_type": "tinvest"},
    )
    assert profile == "type2_tinvest"


def test_migrate_v2_to_v3_adds_schema_profile():
    v2 = migrate_legacy_to_v2(
        {
            "strategy": "momentum_breakout",
            "broker_type": "tinvest",
            "universe_mode": "dms_pipeline",
            "pipeline": {"filters": []},
        }
    )
    out = migrate_v2_to_v3(v2, robot_type=2)
    assert out["config_version"] == CONFIG_VERSION_V3
    assert out["schema_profile"] == "type2_tinvest"
    assert out["broker_type"] == "tinvest"


def test_signal_generation_from_config_accepts_bybit():
    """Regression: history-backtest type2_bybit must not 422 on data_source=bybit."""
    from app.modules.robots.config.migration import signal_generation_from_config

    sig = signal_generation_from_config(
        {
            "config_version": 3,
            "schema_profile": "type2_bybit",
            "broker_type": "bybit",
            "market_profile": "crypto",
            "signal_generation": {
                "strategy": "grain_seed",
                "params": {"interval": "5m"},
                "data_source": "bybit",
                "update_interval_seconds": 10,
            },
        }
    )
    assert sig.data_source == "bybit"
    assert sig.strategy == "grain_seed"
    assert sig.params.get("interval") == "5m"


def test_history_derive_engine_params_bybit_skips_moex_p1():
    from app.modules.robots.service import RobotService

    class _DummyDms:
        pass

    p = RobotService._history_derive_engine_params(
        {
            "config_version": 3,
            "schema_profile": "type2_bybit",
            "broker_type": "bybit",
            "strategy": "grain_seed",
            "signal_generation": {
                "strategy": "grain_seed",
                "params": {"interval": "5m", "candle_days": 14},
                "data_source": "bybit",
            },
            "crypto_universe": {"enabled": True},
            "universe_mode": "auto",
            "risk": {},
            "costs": {},
        },
        dms_service=_DummyDms(),
    )
    assert p["strategy_name"] == "grain_seed"
    assert p["signal_generation"].data_source == "bybit"
    assert p["historical_screening"] is None
    assert p["strategy_params"].get("moex_analysis_interval") is None
    assert p["strategy_params"].get("interval") == "5m"
