import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robots.crypto_universe import ScreeningRow
from app.modules.robots.trading.backtest.universe_reject_report import (
    _format_reject_line,
    build_universe_reject_summary,
    screening_row_to_reject_decision,
)


def test_screening_row_to_reject_decision_includes_metrics():
    row = ScreeningRow(
        symbol="BTCUSDT",
        turnover24h=12_000_000.0,
        lastPrice=65000.0,
        spreadPercent=0.25,
        dailyRangePercent=3.5,
        reject_reason="volume_below_min",
        filter_result="rejected",
    )
    dr = screening_row_to_reject_decision(row, trade_date="2026-05-23")
    assert dr["ticker"] == "BTCUSDT"
    assert dr["reason"] == "volume_below_min"
    assert dr["turnover24h"] == 12_000_000.0
    assert dr["spreadPercent"] == 0.25
    assert dr["dailyRangePercent"] == 3.5


def test_build_summary_groups_by_day_and_reason():
    rows = [
        {
            "trade_date": "2026-05-23",
            "ticker": "BTCUSDT",
            "result": "REJECT",
            "reason": "volume_below_min",
            "turnover24h": 1_000_000,
        },
        {
            "trade_date": "2026-05-23",
            "ticker": "ETHUSDT",
            "result": "REJECT",
            "reason": "spread_above_max",
            "spreadPercent": 0.30,
        },
        {
            "trade_date": "2026-05-24",
            "ticker": "SOLUSDT",
            "result": "REJECT",
            "reason": "volume_below_min",
            "turnover24h": 500_000,
        },
    ]
    filters = {"min_volume_24h_usd": 32_500_000, "max_spread_pct": 0.15}
    summary = build_universe_reject_summary(rows, filters=filters, sample_per_reason=2)
    assert summary["totals"]["rejects"] == 3
    assert summary["by_reason"]["volume_below_min"] == 2
    assert summary["by_day"]["2026-05-23"]["rejects"] == 2
    assert len(summary["samples_by_reason"]["volume_below_min"]) == 2


def test_format_reject_line_shows_thresholds():
    dr = {
        "trade_date": "2026-05-23",
        "ticker": "BTCUSDT",
        "reason": "volume_below_min",
        "turnover24h": 12_000_000,
    }
    line = _format_reject_line(dr, {"min_volume_24h_usd": 32_500_000})
    assert "BTCUSDT" in line
    assert "volume=12,000,000" in line
    assert "min=32,500,000" in line
    assert "spread=" not in line


def test_format_reject_line_spread_in_percent():
    dr = {
        "trade_date": "2026-05-23",
        "ticker": "ETHUSDT",
        "reason": "spread_above_max",
        "spreadPercent": 0.30,
    }
    line = _format_reject_line(dr, {"max_spread_pct": 0.15})
    assert "spread=0.3000% > max=0.1500%" in line
