"""Unit tests for universe mode helpers (live + history-backtest)."""
from __future__ import annotations

from app.modules.robots.universe import (
    UNIVERSE_MODE_DMS,
    UNIVERSE_MODE_FIXED,
    UNIVERSE_MODE_TQBR,
    normalize_universe_mode,
    universe_filter_snapshot_row,
    universe_pipeline_filters,
    universe_whitelist_tickers,
)


def test_normalize_universe_mode_explicit():
    assert normalize_universe_mode({"universe_mode": "tqbr_scan"}) == UNIVERSE_MODE_TQBR


def test_universe_pipeline_filters_only_for_dms():
    filters = [{"type": "volume", "min": 1_000_000}]
    assert universe_pipeline_filters({"universe_mode": "dms_pipeline"}, filters) == filters
    assert universe_pipeline_filters({"universe_mode": "tqbr_scan"}, filters) == []
    assert universe_pipeline_filters({"universe_mode": "fixed", "fixed_tickers": ["SBER"]}, filters) == []


def test_universe_whitelist_only_fixed():
    assert universe_whitelist_tickers({"universe_mode": "tqbr_scan"}) is None
    assert universe_whitelist_tickers({"universe_mode": "fixed", "fixed_tickers": ["SBER"]}) == {"SBER"}


def test_universe_filter_snapshot_row_tqbr_tradable():
    row = {"ticker": "SBER", "security_status": "A", "trading_status": "T"}
    cfg = {"universe_mode": "tqbr_scan"}
    assert universe_filter_snapshot_row(row, cfg) is True


def test_universe_filter_snapshot_row_tqbr_not_trading():
    row = {"ticker": "SBER", "security_status": "A", "trading_status": "H"}
    cfg = {"universe_mode": "tqbr_scan"}
    assert universe_filter_snapshot_row(row, cfg) is False


def test_universe_filter_snapshot_row_fixed():
    cfg = {"universe_mode": "fixed", "fixed_tickers": ["SBER", "GAZP"]}
    assert universe_filter_snapshot_row({"ticker": "SBER"}, cfg) is True
    assert universe_filter_snapshot_row({"ticker": "LKOH"}, cfg) is False


def test_universe_filter_snapshot_row_dms_all():
    cfg = {"universe_mode": "dms_pipeline"}
    assert universe_filter_snapshot_row({"ticker": "ANY"}, cfg) is True
