from __future__ import annotations

import asyncio
import os
from datetime import date
from unittest.mock import MagicMock

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import app.modules.robots.trading.data.providers.bybit_market as bybit_market
from app.modules.robots.trading.intervals import resolve_strategy_interval, strategy_interval_to_bybit_kline


class _FakeBybitClient:
    def __init__(self, *args, **kwargs):
        self.closed = False

    async def get_kline(self, *, category: str, symbol: str, interval: str, start_ms: int, end_ms: int, limit: int):
        assert category == "linear"
        assert interval in {"1", "5", "60", "D"}
        return {
            "retCode": 0,
            "result": {
                "list": [
                    [str(start_ms), "100", "110", "90", "105", "10", "1000"],
                    [str(start_ms + 60_000), "105", "111", "101", "109", "11", "1200"],
                ]
            },
        }

    async def get_funding_history(
        self,
        *,
        category: str,
        symbol: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 200,
    ):
        assert category == "linear"
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": symbol,
                        "fundingRate": "0.0001",
                        "fundingRateTimestamp": str(start_ms or 1_704_067_200_000),
                    }
                ]
            },
        }

    async def close(self):
        self.closed = True


def test_strategy_interval_to_bybit():
    assert strategy_interval_to_bybit_kline("CANDLE_INTERVAL_1_MIN") == "1"
    assert strategy_interval_to_bybit_kline("CANDLE_INTERVAL_5_MIN") == "5"
    assert strategy_interval_to_bybit_kline("CANDLE_INTERVAL_HOUR") == "60"
    assert strategy_interval_to_bybit_kline("CANDLE_INTERVAL_DAY") == "D"


def test_ensure_candles_bybit_market_writes_rows(monkeypatch):
    monkeypatch.setattr(bybit_market, "BybitHttpClient", _FakeBybitClient)
    monkeypatch.setattr(
        bybit_market,
        "_candles_fetch_ranges_for_symbol",
        lambda *args, **kwargs: [(date(2024, 1, 1), date(2024, 1, 2))],
    )
    db = MagicMock()
    resolved = resolve_strategy_interval("CANDLE_INTERVAL_5_MIN")

    async def _run():
        stats = await bybit_market.ensure_candles_bybit_market(
            db,
            symbols=["BTCUSDT", "ETHUSDT"],
            resolved=resolved,
            from_date=date(2024, 1, 1),
            till_date=date(2024, 1, 2),
            testnet=True,
        )
        return stats

    stats = asyncio.run(_run())
    assert stats.total_tickers == 2
    assert stats.processed_tickers == 2
    assert stats.fetched_tickers == 2
    assert stats.fetched_candles == 4
    assert db.execute.call_count >= 4


def test_ensure_funding_bybit_market_writes_rows(monkeypatch):
    monkeypatch.setattr(bybit_market, "BybitHttpClient", _FakeBybitClient)
    from datetime import date as d, datetime, timezone

    miss_audit = bybit_market.FundingCacheAudit(
        symbol="BTCUSDT",
        instrument_category="linear",
        from_date=d(2024, 1, 1),
        till_date=d(2024, 1, 3),
        cached_count=0,
        min_funding_time=None,
        expected_full=9,
        expected_effective=9,
        effective_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
        covers=False,
    )
    monkeypatch.setattr(
        bybit_market,
        "_audit_funding_cache_for_symbol",
        lambda *args, **kwargs: miss_audit,
    )
    db = MagicMock()

    async def _run():
        stats = await bybit_market.ensure_funding_bybit_market(
            db,
            symbols=["BTCUSDT"],
            from_date=date(2024, 1, 1),
            till_date=date(2024, 1, 3),
            instrument_category="linear",
            testnet=True,
        )
        return stats

    stats = asyncio.run(_run())
    assert stats.total_symbols == 1
    assert stats.fetched_symbols == 1
    assert stats.fetched_rows == 1
    assert db.execute.call_count >= 1
    assert db.commit.called


def test_ensure_candles_cache_hit_skips_api(monkeypatch):
    monkeypatch.setattr(bybit_market, "BybitHttpClient", _FakeBybitClient)
    from datetime import date as d

    hit_audit = bybit_market.CandlesCacheAudit(
        symbol="BTCUSDT",
        interval_label="D1",
        interval_code=24,
        from_date=d(2024, 1, 1),
        till_date=d(2024, 1, 30),
        expected_days=30,
        cached_days_count=30,
        cached_min=d(2024, 1, 1),
        cached_max=d(2024, 1, 30),
        missing_raw_count=0,
        pre_listing_skipped_count=0,
        missing_final_count=0,
        fetch_ranges=[],
    )
    monkeypatch.setattr(
        bybit_market,
        "_audit_candles_cache_for_symbol",
        lambda *args, **kwargs: hit_audit,
    )
    db = MagicMock()
    resolved = resolve_strategy_interval("CANDLE_INTERVAL_DAY")

    async def _run():
        return await bybit_market.ensure_candles_bybit_market(
            db,
            symbols=["BTCUSDT"],
            resolved=resolved,
            from_date=date(2024, 1, 1),
            till_date=date(2024, 1, 30),
            testnet=True,
        )

    stats = asyncio.run(_run())
    assert stats.total_tickers == 1
    assert stats.cache_full_hits == 1
    assert stats.fetched_tickers == 0
    assert stats.fetched_candles == 0


def test_screening_d1_prefetch_range_includes_lookback():
    from datetime import date as d

    cfg = {"crypto_universe": {"lookback_days": 20, "atr_period": 14}}
    from_d, till_d = bybit_market.screening_d1_prefetch_range(
        [d(2026, 6, 8), d(2026, 6, 14)],
        cfg,
    )
    assert till_d == d(2026, 6, 13)
    assert from_d < d(2026, 6, 8)


def test_ensure_funding_skips_spot():
    db = MagicMock()

    async def _run():
        return await bybit_market.ensure_funding_bybit_market(
            db,
            symbols=["BTCUSDT"],
            from_date=date(2024, 1, 1),
            till_date=date(2024, 1, 2),
            instrument_category="spot",
        )

    stats = asyncio.run(_run())
    assert stats.total_symbols == 0


async def _screening_symbols_btc(*_args, **_kwargs):
    return ["BTCUSDT"]


def test_ensure_crypto_screening_funding_history_prefetch(monkeypatch):
    monkeypatch.setattr(bybit_market, "BybitHttpClient", _FakeBybitClient)
    from datetime import date as d, datetime, timezone

    miss_audit = bybit_market.FundingCacheAudit(
        symbol="BTCUSDT",
        instrument_category="linear",
        from_date=d(2026, 5, 1),
        till_date=d(2026, 5, 24),
        cached_count=0,
        min_funding_time=None,
        expected_full=72,
        expected_effective=72,
        effective_from=datetime(2026, 5, 1, tzinfo=timezone.utc),
        covers=False,
    )
    monkeypatch.setattr(
        bybit_market,
        "_audit_funding_cache_for_symbol",
        lambda *args, **kwargs: miss_audit,
    )
    monkeypatch.setattr(bybit_market, "resolve_crypto_screening_symbols", _screening_symbols_btc)
    db = MagicMock()

    async def _run():
        return await bybit_market.ensure_crypto_screening_funding_history(
            db,
            trade_dates=[date(2026, 5, 23), date(2026, 5, 24)],
            config={"bybit": {"instrument_category": "linear"}, "crypto_universe": {"lookback_days": 7}},
        )

    stats = asyncio.run(_run())
    assert stats.total_symbols == 1
    assert stats.fetched_symbols == 1
    assert stats.fetched_rows == 1
    assert db.commit.called


def test_candles_fetch_ranges_detects_hole_in_middle(monkeypatch):
    from datetime import date as d

    cached = {d(2024, 1, 1), d(2024, 1, 2), d(2024, 1, 4), d(2024, 1, 5)}
    monkeypatch.setattr(
        bybit_market,
        "_complete_candle_days_in_range",
        lambda *args, **kwargs: cached,
    )
    ranges = bybit_market._candles_fetch_ranges_for_symbol(
        MagicMock(),
        symbol="BTCUSDT",
        interval_label="D1",
        from_date=d(2024, 1, 1),
        till_date=d(2024, 1, 5),
    )
    assert ranges == [(d(2024, 1, 3), d(2024, 1, 3))]


def test_candles_fetch_ranges_empty_when_all_days_cached(monkeypatch):
    from datetime import date as d

    cached = {d(2024, 1, 1), d(2024, 1, 2), d(2024, 1, 3)}
    monkeypatch.setattr(
        bybit_market,
        "_complete_candle_days_in_range",
        lambda *args, **kwargs: cached,
    )
    ranges = bybit_market._candles_fetch_ranges_for_symbol(
        MagicMock(),
        symbol="BTCUSDT",
        interval_label="D1",
        from_date=d(2024, 1, 1),
        till_date=d(2024, 1, 3),
    )
    assert ranges == []


def test_candles_fetch_skips_pre_listing_gap(monkeypatch):
    from datetime import date as d

    # Listed 2026-05-01; lookback from 2026-04-18 has no pre-listing candles on Bybit.
    cached = {d(2026, 5, 1), d(2026, 5, 2), d(2026, 5, 3)}
    monkeypatch.setattr(
        bybit_market,
        "_complete_candle_days_in_range",
        lambda *args, **kwargs: cached,
    )
    ranges = bybit_market._candles_fetch_ranges_for_symbol(
        MagicMock(),
        symbol="NOWUSDT",
        interval_label="D1",
        from_date=d(2026, 4, 18),
        till_date=d(2026, 5, 3),
    )
    assert ranges == []


def test_candles_cache_audit_format_pre_listing():
    from datetime import date as d

    audit = bybit_market.CandlesCacheAudit(
        symbol="NOWUSDT",
        interval_label="D1",
        interval_code=24,
        from_date=d(2026, 4, 18),
        till_date=d(2026, 5, 3),
        expected_days=16,
        cached_days_count=3,
        cached_min=d(2026, 5, 1),
        cached_max=d(2026, 5, 3),
        missing_raw_count=13,
        pre_listing_skipped_count=13,
        missing_final_count=0,
        fetch_ranges=[],
    )
    line = audit.format_line(idx=1, total=595)
    assert "NOWUSDT" in line
    assert "action=HIT" in line
    assert "pre_listing_gap_ignored" in line


def test_funding_cache_audit_format():
    from datetime import date as d, datetime, timezone

    audit = bybit_market.FundingCacheAudit(
        symbol="NOWUSDT",
        instrument_category="linear",
        from_date=d(2026, 4, 18),
        till_date=d(2026, 6, 23),
        cached_count=186,
        min_funding_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
        expected_full=300,
        expected_effective=162,
        effective_from=datetime(2026, 5, 1, tzinfo=timezone.utc),
        covers=True,
    )
    line = audit.format_line(idx=2, total=595)
    assert "action=HIT" in line
    assert "expected_effective=162" in line


def test_funding_cache_covers_range_respects_listing_start():
    from datetime import datetime, timezone

    db = MagicMock()
    listing = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    db.execute.return_value.mappings.return_value.first.return_value = {
        "cnt": 186,
        "min_ft": listing,
    }
    covered = bybit_market._funding_cache_covers_range(
        db,
        symbol="NOWUSDT",
        instrument_category="linear",
        from_dt=datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc),
        to_dt_exclusive=datetime(2026, 6, 24, 0, 0, tzinfo=timezone.utc),
    )
    assert covered is True


def test_expected_bars_per_day_intraday():
    assert bybit_market._expected_bars_per_day(5) == 288
    assert bybit_market._min_bars_per_day(5) == 273
    assert bybit_market._expected_bars_per_day(24) == 1
    assert bybit_market._min_bars_per_day(24) == 1


def test_audit_m5_partial_day_triggers_fetch(monkeypatch):
    from datetime import date as d

    bar_counts = {d(2024, 1, 1): 50}
    monkeypatch.setattr(bybit_market, "_candles_bar_counts_by_day", lambda *args, **kwargs: bar_counts)
    audit = bybit_market._audit_candles_cache_for_symbol(
        MagicMock(),
        symbol="BTCUSDT",
        interval_label="M5",
        interval_code=5,
        from_date=d(2024, 1, 1),
        till_date=d(2024, 1, 1),
    )
    assert audit.fetch_ranges == [(d(2024, 1, 1), d(2024, 1, 1))]
    assert audit.min_bars_per_day == 273


def test_candles_cache_audit_format_m5():
    from datetime import date as d

    audit = bybit_market.CandlesCacheAudit(
        symbol="BTCUSDT",
        interval_label="M5",
        interval_code=5,
        from_date=d(2024, 1, 1),
        till_date=d(2024, 1, 2),
        expected_days=2,
        cached_days_count=1,
        cached_min=d(2024, 1, 1),
        cached_max=d(2024, 1, 1),
        missing_raw_count=1,
        pre_listing_skipped_count=0,
        missing_final_count=1,
        min_bars_per_day=273,
        fetch_ranges=[(d(2024, 1, 2), d(2024, 1, 2))],
    )
    line = audit.format_line(idx=1, total=10)
    assert "CACHE | M5 |" in line
    assert "min_bars/day=273" in line
    assert "action=FETCH" in line


def test_fetch_kline_history_paginates():
    from datetime import datetime, timezone

    class _PagingClient:
        def __init__(self):
            self.end_ms_seen: list[int] = []

        async def get_kline(self, **kwargs):
            start_ms = int(kwargs["start_ms"])
            end_ms = int(kwargs["end_ms"])
            limit = int(kwargs["limit"])
            self.end_ms_seen.append(end_ms)
            if len(self.end_ms_seen) == 1:
                rows = [
                    [str(end_ms - i * 300_000), "1", "1", "1", "1", "1", "1"]
                    for i in range(limit)
                ]
                return {"result": {"list": rows}}
            return {"result": {"list": [[str(start_ms), "1", "1", "1", "1", "1", "1"]]}}

    async def _run():
        client = _PagingClient()
        from_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        to_dt = datetime(2024, 1, 5, tzinfo=timezone.utc)
        rows = await bybit_market.fetch_kline_history(
            client,
            category="linear",
            symbol="BTCUSDT",
            bybit_interval="5",
            from_dt=from_dt,
            to_dt_exclusive=to_dt,
        )
        return client, rows

    client, rows = asyncio.run(_run())
    assert len(client.end_ms_seen) == 2
    assert len(rows) == bybit_market.BYBIT_KLINE_PAGE_LIMIT + 1
