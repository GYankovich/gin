from __future__ import annotations

from app.modules.recommendations.optimization_failure_hints import (
    build_failure_insights,
    build_suggested_changes,
    classify_backtest_failure,
    parse_top_rejects,
)


def test_parse_top_rejects_from_run_153_style_error():
    msg = (
        "Нет бумаг для бэктеста за выбранный период "
        "(processed=31, skipped_fetch=0, skipped_empty=0, trade_dates=31, "
        "top_rejects=volume_below_min x16650; spread_above_max x65)"
    )
    rejects = parse_top_rejects(msg)
    assert rejects["volume_below_min"] == 16650
    assert rejects["spread_above_max"] == 65
    assert classify_backtest_failure(msg) == "no_universe"


def test_build_suggested_changes_volume_and_spread():
    config = {
        "crypto_universe": {
            "min_volume_24h_usd": 50_000_000,
            "max_spread_bps": 15,
        }
    }
    changes = build_suggested_changes(
        {"volume_below_min": 100, "spread_above_max": 5},
        config,
    )
    paths = {c["path"] for c in changes}
    assert "crypto_universe.min_volume_24h_usd" in paths
    assert "crypto_universe.max_spread_bps" in paths
    vol = next(c for c in changes if c["path"] == "crypto_universe.min_volume_24h_usd")
    spread = next(c for c in changes if c["path"] == "crypto_universe.max_spread_bps")
    assert vol["suggested_value"] < 50_000_000
    assert spread["suggested_value"] > 15


def test_build_failure_insights_no_universe_without_top_rejects():
    insights = build_failure_insights("Нет бумаг для бэктеста за выбранный период (processed=1)", {})
    assert insights["failure_category"] == "no_universe"
    assert len(insights["suggested_changes"]) >= 1
