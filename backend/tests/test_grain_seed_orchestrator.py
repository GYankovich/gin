"""Юнит-тесты оркестрации grain_seed (без торговой сессии)."""
from datetime import date

from app.modules.tinvest.facade import TInvestFacade
from app.modules.robots.trading.grain_seed_orchestrator import (
    GrainSeedOrchestrationResult,
    compute_effective_free_funds,
    count_consecutive_loss_days_from_rows,
    filter_grain_seed_signals,
    parse_force_close_time,
)


def test_parse_force_close_time():
    assert parse_force_close_time("18:45").hour == 18 and parse_force_close_time("18:45").minute == 45
    assert parse_force_close_time("09:05:00").minute == 5


def test_compute_effective_free_funds():
    assert compute_effective_free_funds(100.0, 50.0) == 50.0
    assert compute_effective_free_funds(100.0, 0.0) == 100.0


def test_count_consecutive_loss_days_from_rows():
    rows = [
        (date(2026, 4, 15), -10.0),
        (date(2026, 4, 14), -5.0),
        (date(2026, 4, 13), 1.0),
    ]
    assert count_consecutive_loss_days_from_rows(rows) == 2
    assert count_consecutive_loss_days_from_rows([(date(2026, 4, 15), 1.0)]) == 0


def test_filter_grain_seed_signals_drops_buy_when_blocked():
    orch = GrainSeedOrchestrationResult(
        block_new_entries=True,
        block_reason="test",
        effective_free_funds=0.0,
        allow_only_reduce=False,
        broker_non_currency_figis=frozenset(),
        db_open_figis=frozenset(),
        position_mismatch=False,
    )
    sigs = [
        {"figi": "f1", "signal": "BUY"},
        {"figi": "f2", "signal": "SELL"},
    ]
    out = filter_grain_seed_signals(sigs, orch)
    assert len(out) == 1
    assert out[0]["signal"] == "SELL"


def test_filter_grain_seed_signals_drops_buy_after_force_time_only():
    orch = GrainSeedOrchestrationResult(
        block_new_entries=False,
        block_reason="",
        effective_free_funds=100.0,
        allow_only_reduce=True,
        broker_non_currency_figis=frozenset(),
        db_open_figis=frozenset(),
        position_mismatch=False,
    )
    sigs = [{"figi": "f1", "signal": "BUY"}, {"figi": "f2", "signal": "SELL"}]
    out = filter_grain_seed_signals(sigs, orch)
    assert len(out) == 1 and out[0]["signal"] == "SELL"


def test_compute_free_funds_subtracts_futures_margin_when_present():
    p = {
        "total_amount_currencies": {"decimal": 1000.0, "currency": "RUB"},
        "futures_margin": {"decimal": 200.0, "currency": "RUB"},
        "positions": [],
    }
    assert TInvestFacade.compute_free_funds_from_portfolio(p) == 800.0


def test_filter_grain_seed_signals_allows_all_when_clear():
    orch = GrainSeedOrchestrationResult(
        block_new_entries=False,
        block_reason="",
        effective_free_funds=100.0,
        allow_only_reduce=False,
        broker_non_currency_figis=frozenset(),
        db_open_figis=frozenset(),
        position_mismatch=False,
    )
    sigs = [{"figi": "f1", "signal": "BUY"}]
    assert len(filter_grain_seed_signals(sigs, orch)) == 1
