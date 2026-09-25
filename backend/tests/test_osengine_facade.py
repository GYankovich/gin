"""Unit tests for OsEngine coverage + facade orchestration (no external IO)."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Tuple
from unittest.mock import MagicMock

from app.modules.osengine.coverage import expand_lookback, merge_ranges, missing_ranges
from app.modules.osengine.facade import DefaultOsEngineFacade, build_candle_ensure_request
from app.modules.osengine.providers import InMemoryLeaseStore, UnconfiguredHistoryProvider
from app.modules.osengine.types import CacheLease, TimeRange


def test_merge_ranges_overlaps_and_adjacent():
    merged = merge_ranges(
        [
            TimeRange(date(2024, 1, 1), date(2024, 1, 10)),
            TimeRange(date(2024, 1, 8), date(2024, 1, 20)),
            TimeRange(date(2024, 1, 20), date(2024, 1, 25)),
            TimeRange(date(2024, 3, 1), date(2024, 3, 5)),
        ]
    )
    assert merged == [
        TimeRange(date(2024, 1, 1), date(2024, 1, 25)),
        TimeRange(date(2024, 3, 1), date(2024, 3, 5)),
    ]


def test_missing_ranges_partial_cover():
    needed = TimeRange(date(2024, 1, 1), date(2024, 2, 1))
    covered = [
        TimeRange(date(2024, 1, 5), date(2024, 1, 15)),
        TimeRange(date(2024, 1, 20), date(2024, 1, 25)),
    ]
    gaps = missing_ranges(needed, covered)
    assert gaps == [
        TimeRange(date(2024, 1, 1), date(2024, 1, 5)),
        TimeRange(date(2024, 1, 15), date(2024, 1, 20)),
        TimeRange(date(2024, 1, 25), date(2024, 2, 1)),
    ]


def test_missing_ranges_full_hit():
    needed = TimeRange(date(2024, 1, 1), date(2024, 1, 31))
    covered = [TimeRange(date(2023, 12, 1), date(2024, 2, 1))]
    assert missing_ranges(needed, covered) == []


def test_expand_lookback():
    w = TimeRange(date(2024, 2, 10), date(2024, 2, 20))
    assert expand_lookback(w, 10) == TimeRange(date(2024, 1, 31), date(2024, 2, 20))


class _CountingHistory(UnconfiguredHistoryProvider):
    def __init__(self) -> None:
        self.calls: List[tuple] = []

    async def fetch_candle_gaps(self, db, *, instrument, interval, gaps, progress_callback=None):
        self.calls.append((instrument.cache_id, interval, list(gaps)))
        return 0


def _coverage_map(
    mapping: Dict[Tuple[str, str], List[TimeRange]],
):
    def _lookup(db, market, instrument_id, interval, window):
        return list(mapping.get((instrument_id, interval), []))

    return _lookup


def test_facade_skips_fetch_when_cache_covers_window():
    leases = InMemoryLeaseStore()
    history = _CountingHistory()
    covered = {
        ("SBER", "1m"): [TimeRange(date(2024, 1, 1), date(2024, 6, 1))],
    }
    facade = DefaultOsEngineFacade(
        history=history,
        leases=leases,
        market="osengine",
        coverage_lookup=_coverage_map(covered),
    )
    db = MagicMock()

    req = build_candle_ensure_request(
        run_id=2,
        tickers=["SBER"],
        interval="1m",
        from_date=date(2024, 2, 1),
        till_date=date(2024, 3, 1),
        board="TQBR",
    )
    stats = asyncio.run(facade.ensure_candles_for_backtest(db, req))
    assert stats.cache_full_hits == 1
    assert stats.instruments_with_gaps == 0
    assert history.calls == []
    assert stats.leases_created == 1


def test_facade_fetches_only_gaps():
    leases = InMemoryLeaseStore()
    history = _CountingHistory()
    covered = {
        ("SBER", "1m"): [TimeRange(date(2024, 1, 1), date(2024, 2, 1))],
    }
    facade = DefaultOsEngineFacade(
        history=history,
        leases=leases,
        market="osengine",
        coverage_lookup=_coverage_map(covered),
    )
    db = MagicMock()

    req = build_candle_ensure_request(
        run_id=2,
        tickers=["SBER"],
        interval="1m",
        from_date=date(2024, 1, 15),
        till_date=date(2024, 3, 1),
    )
    stats = asyncio.run(facade.ensure_candles_for_backtest(db, req))
    assert stats.instruments_with_gaps == 1
    assert len(history.calls) == 1
    assert history.calls[0][2] == [TimeRange(date(2024, 2, 1), date(2024, 3, 1))]


def test_release_and_gc_cooling_leases():
    leases = InMemoryLeaseStore()
    facade = DefaultOsEngineFacade(leases=leases, market="osengine")
    db = MagicMock()
    leases.create_leases(
        db,
        run_id=7,
        market="osengine",
        instrument_ids=["GAZP"],
        interval="1d",
        window=TimeRange(date(2024, 1, 1), date(2024, 1, 10)),
    )
    rel = facade.release_backtest_leases(db, run_id=7, success=True)
    assert rel.leases_touched == 1

    old = leases._leases[0]
    assert old.expires_at is not None
    leases._leases[0] = CacheLease(
        id=old.id,
        run_id=old.run_id,
        market=old.market,
        instrument_id=old.instrument_id,
        interval=old.interval,
        from_date=old.from_date,
        to_date=old.to_date,
        status=old.status,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    gc = facade.gc_cache(db)
    assert gc.expired_leases == 1


def test_facade_runs_gc_before_ensure(monkeypatch):
    leases = InMemoryLeaseStore()
    history = _CountingHistory()
    gc_calls = {"n": 0}

    class _Facade(DefaultOsEngineFacade):
        def gc_cache(self, db):
            gc_calls["n"] += 1
            return super().gc_cache(db)

    facade = _Facade(
        history=history,
        leases=leases,
        market="osengine",
        coverage_lookup=_coverage_map({}),
    )
    monkeypatch.setattr(
        "app.modules.osengine.facade.settings.OSENGINE_CACHE_GC_ON_BACKTEST_START",
        True,
    )
    req = build_candle_ensure_request(
        run_id=3,
        tickers=["SBER"],
        interval="1m",
        from_date=date(2024, 1, 1),
        till_date=date(2024, 1, 5),
    )
    asyncio.run(facade.ensure_candles_for_backtest(MagicMock(), req))
    assert gc_calls["n"] == 1


def test_facade_skips_gc_when_flag_off(monkeypatch):
    leases = InMemoryLeaseStore()
    history = _CountingHistory()
    gc_calls = {"n": 0}

    class _Facade(DefaultOsEngineFacade):
        def gc_cache(self, db):
            gc_calls["n"] += 1
            return super().gc_cache(db)

    facade = _Facade(
        history=history,
        leases=leases,
        market="osengine",
        coverage_lookup=_coverage_map({}),
    )
    monkeypatch.setattr(
        "app.modules.osengine.facade.settings.OSENGINE_CACHE_GC_ON_BACKTEST_START",
        False,
    )
    req = build_candle_ensure_request(
        run_id=4,
        tickers=["SBER"],
        interval="1m",
        from_date=date(2024, 1, 1),
        till_date=date(2024, 1, 5),
    )
    asyncio.run(facade.ensure_candles_for_backtest(MagicMock(), req))
    assert gc_calls["n"] == 0


def test_prefetch_routes_to_osengine(monkeypatch):
    from datetime import date as date_cls

    from app.modules.robots.trading.backtest import candle_prefetch
    from app.modules.robots.trading.intervals import resolve_strategy_interval
    from app.modules.osengine.stats import EnsureCandlesStats
    import app.modules.osengine as ose_mod

    calls = {}

    class _FakeFacade:
        async def ensure_candles_for_backtest(self, db, request, **kwargs):
            calls["request"] = request
            return EnsureCandlesStats(
                run_id=request.run_id,
                interval=request.interval,
                total_instruments=len(request.instruments),
                cache_full_hits=1,
            )

    monkeypatch.setattr(ose_mod, "get_osengine_facade", lambda: _FakeFacade())

    resolved = resolve_strategy_interval("M5")
    stats = asyncio.run(
        candle_prefetch.prefetch_candles_for_backtest(
            MagicMock(),
            board="TQBR",
            tickers=["SBER"],
            resolved=resolved,
            from_date=date_cls(2024, 1, 1),
            till_date=date_cls(2024, 1, 10),
            run_id=99,
            source="moex",  # TEMP: even non-osengine sources route to OsEngine
        )
    )
    assert calls["request"].run_id == 99
    assert stats.cache_full_hits == 1
    assert stats.total_tickers == 1
    assert candle_prefetch.use_osengine_source("tinvest") is True
