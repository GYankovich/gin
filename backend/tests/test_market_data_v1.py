import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.market_data_v1 import gaps as gap_util
from app.modules.market_data_v1.intervals import moex_interval_code
from app.modules.market_data_v1.schemas import CandleLoadJobCreate


def test_moex_interval_code_daily_and_hourly():
    assert moex_interval_code("1d") == 24
    assert moex_interval_code("1h") == 60


def test_moex_interval_code_rejects_unknown():
    with pytest.raises(ValueError, match="unsupported"):
        moex_interval_code("2s")


def test_candle_load_job_create_accepts_from_alias():
    body = CandleLoadJobCreate.model_validate(
        {
            "tickers": ["sber", " gazp "],
            "board": "tqbr",
            "interval": "1d",
            "from": "2024-01-01T00:00:00+00:00",
            "to": "2024-06-01T00:00:00+00:00",
        }
    )
    assert body.tickers == ["SBER", "GAZP"]
    assert body.board == "TQBR"
    assert body.from_.year == 2024


def test_compute_moex_fetch_ranges_full_window_when_empty():
    f = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t = datetime(2024, 6, 1, tzinfo=timezone.utc)
    assert gap_util.compute_moex_fetch_ranges([], f, t, "1d") == [(f, t)]


def test_compute_moex_fetch_ranges_daily_calendar_splits_weekends():
    """После последнего кешированного будни остаются пропуски; выходные не требуют дневного бара."""
    f = datetime(2024, 1, 2, tzinfo=timezone.utc)
    t = datetime(2024, 1, 10, tzinfo=timezone.utc)
    existing = [
        datetime(2024, 1, 2, tzinfo=timezone.utc),
        datetime(2024, 1, 3, tzinfo=timezone.utc),
        datetime(2024, 1, 4, tzinfo=timezone.utc),
    ]
    ranges = gap_util.compute_moex_fetch_ranges(existing, f, t, "1d")
    assert len(ranges) == 2
    assert ranges[0] == (
        datetime(2024, 1, 5, tzinfo=timezone.utc),
        datetime(2024, 1, 6, tzinfo=timezone.utc),
    )
    assert ranges[1][0] == datetime(2024, 1, 8, tzinfo=timezone.utc)
    assert ranges[1][1] == datetime(2024, 1, 11, tzinfo=timezone.utc)


def test_compute_moex_fetch_ranges_daily_calendar_sparse_bars():
    """Только два дня в кеше — календарь будней даёт несколько отрезков дыр (разрывы выходными)."""
    f = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t = datetime(2024, 1, 31, tzinfo=timezone.utc)
    mid_start = datetime(2024, 1, 10, tzinfo=timezone.utc)
    mid_end = datetime(2024, 1, 20, tzinfo=timezone.utc)
    existing = [mid_start, mid_end]
    ranges = gap_util.compute_moex_fetch_ranges(existing, f, t, "1d")
    assert len(ranges) >= 3
    assert ranges[0][0] == f
    assert ranges[-1][1] == datetime(2024, 2, 1, tzinfo=timezone.utc)


def test_compute_moex_fetch_ranges_daily_calendar_finds_weekday_holes():
    """Между двумя якорными датами отсутствуют будни — не один непрерывный интервал datetime, а несколько по календарю."""
    f = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t = datetime(2024, 2, 1, tzinfo=timezone.utc)
    a = datetime(2024, 1, 5, tzinfo=timezone.utc)
    b = datetime(2024, 1, 20, tzinfo=timezone.utc)
    existing = [a, b]
    ranges = gap_util.compute_moex_fetch_ranges(existing, f, t, "1d")
    assert len(ranges) >= 3
    assert all(lo < hi for lo, hi in ranges)


def test_expected_bar_count_1d_matches_weekdays():
    f = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t = datetime(2024, 1, 31, tzinfo=timezone.utc)
    w = gap_util.count_weekdays_in_date_range(f.date(), t.date())
    assert gap_util.expected_bar_count_upper_bound(f, t, "1d") == w + 1


def test_daily_calendar_single_missing_weekday_between_anchors():
    mon = datetime(2024, 1, 8, tzinfo=timezone.utc)
    wed = datetime(2024, 1, 10, tzinfo=timezone.utc)
    ranges = gap_util.compute_moex_fetch_ranges([mon, wed], mon, wed, "1d")
    assert len(ranges) == 1
    assert ranges[0] == (
        datetime(2024, 1, 9, tzinfo=timezone.utc),
        datetime(2024, 1, 10, tzinfo=timezone.utc),
    )


def test_intraday_calendar_chunk_gap_ranges_detects_shortage():
    f = datetime(2024, 1, 2, tzinfo=timezone.utc)
    t = datetime(2024, 1, 17, tzinfo=timezone.utc)
    sparse = [f + timedelta(hours=h) for h in (0, 1, 2, 3, 4)]
    ranges = gap_util.intraday_calendar_chunk_gap_ranges(sparse, f, t, "1h")
    assert ranges


def test_merge_ranges_overlapping_only():
    f = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t0 = datetime(2024, 1, 10, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 15, tzinfo=timezone.utc)
    t2 = datetime(2024, 2, 1, tzinfo=timezone.utc)
    merged = gap_util.merge_ranges([(f, t1), (t0, t2)])
    assert merged == [(f, t2)]


def test_merge_ranges_touching_not_merged():
    f = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t0 = datetime(2024, 1, 10, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 20, tzinfo=timezone.utc)
    t2 = datetime(2024, 2, 1, tzinfo=timezone.utc)
    merged = gap_util.merge_ranges([(f, t0), (t0, t1), (t1, t2)])
    assert merged == [(f, t0), (t0, t1), (t1, t2)]
