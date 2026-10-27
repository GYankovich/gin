"""Paper cycle bar clock: close a timeframe bar once, do not repaint history."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots_v2.engine.live_bars import (
    closed_bars_ready,
    floor_bar_open,
    merge_closed_candles,
    parse_moex_candle_begin,
    series_needs_roll,
    update_forming_bar,
)
from app.modules.robots_v2.engine.market_data import (
    parse_moex_candles_payload,
    parse_moex_marketdata_last,
    rest_marks_to_store,
)
from app.modules.trading_core.contracts import Candle


def _bar(hour: int, *, volume: int = 100, close: float = 10.0) -> Candle:
    return Candle(
        interval="1h",
        time=datetime(2026, 10, 16, hour, 0, tzinfo=timezone.utc),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
        secid="NVTK",
    )


def test_moex_begin_is_moscow_wall_time():
    opened = parse_moex_candle_begin("2026-10-16 10:00:00")
    assert opened == datetime(2026, 10, 16, 7, 0, tzinfo=timezone.utc)


def test_roll_once_per_hour_and_incoming_volume_replaces_synthetic():
    hist = [_bar(6, volume=0, close=10.0), _bar(7, volume=0, close=11.0)]
    incoming = [_bar(7, volume=5000, close=12.0), _bar(8, volume=9000, close=13.0)]
    forming = datetime(2026, 10, 16, 8, 30, tzinfo=timezone.utc)
    merged = merge_closed_candles(hist, incoming, forming_open=forming, minutes=60)
    assert [c.time.hour for c in merged] == [6, 7]
    assert merged[-1].volume == 5000
    assert merged[-1].close == 12.0
    assert merged[0].volume == 0


def test_forming_update_does_not_repaint_a_closed_bar():
    closed = _bar(7, volume=4000, close=12.0)
    now = datetime(2026, 10, 16, 8, 5, tzinfo=timezone.utc)
    hist = update_forming_bar(
        [closed], price=15.0, now=now, minutes=60, timeframe="1h", ticker="NVTK",
    )
    assert len(hist) == 2
    assert hist[0].close == 12.0
    assert hist[0].volume == 4000
    assert hist[1].time == datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    assert hist[1].close == 15.0
    again = update_forming_bar(
        hist, price=16.0, now=now + timedelta(minutes=10), minutes=60, timeframe="1h", ticker="NVTK",
    )
    assert len(again) == 2
    assert again[0].volume == 4000
    assert again[1].close == 16.0
    assert again[1].high == 16.0


def test_series_needs_roll_latches_on_the_open():
    now = datetime(2026, 10, 16, 8, 5, tzinfo=timezone.utc)
    histories = {"NVTK": [_bar(7, volume=10)]}
    assert series_needs_roll(histories, now=now, minutes=60, committed_open=None)
    committed = floor_bar_open(now, 60)
    assert not series_needs_roll(histories, now=now, minutes=60, committed_open=committed)


def test_closed_bars_ready_waits_for_volume():
    forming = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    empty_vol = {"NVTK": [_bar(7, volume=0)]}
    assert not closed_bars_ready(empty_vol, forming_open=forming, minutes=60)
    filled = {"NVTK": [_bar(7, volume=1200)]}
    assert closed_bars_ready(filled, forming_open=forming, minutes=60)


def test_poll_stores_prices_already_known():
    stored = rest_marks_to_store(
        seed_from_ws=False,
        fetched={"NVTK": 1102.5, "SBER": 310.0},
        gap_fill={},
    )
    assert stored == {"NVTK": 1102.5, "SBER": 310.0}


def test_scalper_tick_does_not_overwrite_tape():
    stored = rest_marks_to_store(
        seed_from_ws=True,
        fetched={"NVTK": 1102.5},
        gap_fill={"SBER": 300.0},
    )
    assert stored == {"SBER": 300.0}


def test_parse_last_prefers_last_over_close():
    payload = {
        "marketdata": {
            "columns": ["SECID", "LAST", "LCLOSEPRICE"],
            "data": [
                ["NVTK", 1102.5, 1090.0],
                ["SBER", None, 310.0],
                ["GAZP", None, None],
            ],
        }
    }
    assert parse_moex_marketdata_last(payload, ["NVTK", "SBER", "GAZP"]) == {
        "NVTK": 1102.5,
        "SBER": 310.0,
    }


def test_parse_moex_candles_shifts_moscow_begin():
    payload = {
        "candles": {
            "columns": ["begin", "open", "high", "low", "close", "volume"],
            "data": [["2026-10-16 10:00:00", 10, 12, 9, 11, 4200]],
        }
    }
    candles = parse_moex_candles_payload(payload, ticker="nvtk", timeframe="1h")
    assert len(candles) == 1
    assert candles[0].time == datetime(2026, 10, 16, 7, 0, tzinfo=timezone.utc)
    assert candles[0].volume == 4200
    assert candles[0].secid == "NVTK"
