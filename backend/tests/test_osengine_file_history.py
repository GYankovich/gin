"""Tests for OsEngine file history importer."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from app.modules.osengine.candle_parser import parse_candle_line
from app.modules.osengine.facade import DefaultOsEngineFacade, build_candle_ensure_request
from app.modules.osengine.file_index import find_candle_files
from app.modules.osengine.history_files import FileHistoryProvider
from app.modules.osengine.intervals_map import cache_interval_to_osengine_tf, normalize_cache_interval
from app.modules.osengine.providers import InMemoryLeaseStore
from app.modules.osengine.types import InstrumentKey, TimeRange


def test_parse_candle_line_msk_to_utc():
    c = parse_candle_line("20240115,100000,100.5,101,99.5,100.8,12,0", source_tz="Europe/Moscow")
    assert c is not None
    assert c.open == Decimal("100.5")
    assert c.volume == Decimal("12")
    # 10:00 MSK = 07:00 UTC
    assert c.time_start == datetime(2024, 1, 15, 7, 0, 0, tzinfo=timezone.utc)


def test_parse_candle_line_bad():
    assert parse_candle_line("") is None
    assert parse_candle_line("not,a,candle") is None


def test_interval_map():
    assert normalize_cache_interval("M5") == "M5"
    assert normalize_cache_interval("5m") == "M5"
    assert cache_interval_to_osengine_tf("I1") == "Min1"
    assert cache_interval_to_osengine_tf("D1") == "Day"
    assert cache_interval_to_osengine_tf("I10") == "Min10"


def test_find_candle_files_osdata_layout(tmp_path: Path):
    root = tmp_path / "Data"
    f = root / "FinamSet" / "SBER" / "Min1" / "SBER.txt"
    f.parent.mkdir(parents=True)
    f.write_text(
        "20240110,100000,1,1,1,1,1\n"
        "20240111,100000,2,2,2,2,2\n",
        encoding="utf-8",
    )
    hits = find_candle_files(root, instrument=InstrumentKey("SBER"), interval="I1")
    assert len(hits) == 1
    assert hits[0].path == f
    assert hits[0].osengine_tf == "Min1"


def test_file_history_provider_upserts(tmp_path: Path, monkeypatch):
    root = tmp_path / "Data"
    f = root / "SetA" / "SBER" / "Min1" / "SBER.txt"
    f.parent.mkdir(parents=True)
    # 10:00 MSK on Jan 10-12
    f.write_text(
        "\n".join(
            [
                "20240110,100000,10,11,9,10.5,100",
                "20240111,100000,20,21,19,20.5,200",
                "20240112,100000,30,31,29,30.5,300",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    executed = []

    def _execute(sql, params=None):
        executed.append(params)
        return MagicMock()

    db = MagicMock()
    db.execute.side_effect = _execute

    provider = FileHistoryProvider(data_root=str(root), market="osengine", source_tz="Europe/Moscow")
    n = asyncio.run(
        provider.fetch_candle_gaps(
            db,
            instrument=InstrumentKey("SBER", "TQBR"),
            interval="I1",
            gaps=[TimeRange(date(2024, 1, 10), date(2024, 1, 12))],
        )
    )
    # half-open [10, 12) → Jan 10 and Jan 11 only
    assert n == 2
    assert len(executed) == 2
    assert executed[0]["ticker"] == "SBER"
    assert executed[0]["market"] == "osengine"
    assert executed[0]["interval"] == "I1"
    assert executed[0]["open"] == Decimal("10")


def test_facade_loads_from_files_when_cache_empty(tmp_path: Path, monkeypatch):
    root = tmp_path / "Data"
    f = root / "SetA" / "GAZP" / "Day" / "GAZP.txt"
    f.parent.mkdir(parents=True)
    f.write_text("20240201,000000,100,110,90,105,1000\n", encoding="utf-8")

    executed = []

    def _execute(sql, params=None):
        executed.append(params)
        return MagicMock(rowcount=0)

    db = MagicMock()
    db.execute.side_effect = _execute

    history = FileHistoryProvider(data_root=str(root), market="osengine")
    leases = InMemoryLeaseStore()
    facade = DefaultOsEngineFacade(
        history=history,
        leases=leases,
        market="osengine",
        coverage_lookup=lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "app.modules.osengine.facade.settings.OSENGINE_CACHE_GC_ON_BACKTEST_START",
        False,
    )
    req = build_candle_ensure_request(
        run_id=11,
        tickers=["GAZP"],
        interval="D1",
        from_date=date(2024, 2, 1),
        till_date=date(2024, 2, 2),
    )
    stats = asyncio.run(facade.ensure_candles_for_backtest(db, req))
    assert stats.instruments_with_gaps == 1
    assert stats.fetched_candles == 1
    assert stats.leases_created == 1
    assert any(p and p.get("ticker") == "GAZP" for p in executed if isinstance(p, dict))
