from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.robots.crypto_universe import (
    CryptoUniverseFilters,
    ScreeningRow,
    _bulk_load_funding_avg_from_cache,
    _bulk_load_lsr_from_cache,
    _bulk_load_oi_from_cache,
    enrich_derivative_metrics_live,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, rows_by_table: dict[str, list]):
        self.rows_by_table = rows_by_table
        self.executed: list[tuple[str, dict]] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append((sql, params or {}))
        if "bybit_funding_history" in sql and "INSERT" in sql.upper():
            return _FakeResult([])
        if "bybit_open_interest_history" in sql and "INSERT" in sql.upper():
            return _FakeResult([])
        if "bybit_lsr_history" in sql and "INSERT" in sql.upper():
            return _FakeResult([])
        if "bybit_funding_history" in sql:
            return _FakeResult(self.rows_by_table.get("funding", []))
        if "bybit_open_interest_history" in sql:
            return _FakeResult(self.rows_by_table.get("oi", []))
        if "bybit_lsr_history" in sql:
            return _FakeResult(self.rows_by_table.get("lsr", []))
        return _FakeResult([])

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_bulk_load_oi_and_lsr_respect_ttl():
    now = datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc)
    db = _FakeDB(
        {
            "oi": [("BTCUSDT", 12_000_000.0)],
            "lsr": [("BTCUSDT", 0.55, 0.45)],
        }
    )
    oi = _bulk_load_oi_from_cache(
        db, symbols=["BTCUSDT"], category="linear", ttl_minutes=15, now=now
    )
    lsr = _bulk_load_lsr_from_cache(
        db, symbols=["BTCUSDT"], category="linear", ttl_minutes=15, now=now
    )
    assert oi["BTCUSDT"] == pytest.approx(12_000_000.0)
    assert lsr["BTCUSDT"][0] == pytest.approx(0.55 / 0.45)


def test_bulk_load_funding_requires_fresh_print():
    now = datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc)
    stale_ts = now - timedelta(hours=20)
    fresh_ts = now - timedelta(hours=2)
    db_stale = _FakeDB({"funding": [("BTCUSDT", 0.0001, stale_ts)]})
    db_fresh = _FakeDB(
        {
            "funding": [
                ("BTCUSDT", 0.0001, fresh_ts - timedelta(hours=4)),
                ("BTCUSDT", 0.0003, fresh_ts),
            ]
        }
    )
    assert (
        _bulk_load_funding_avg_from_cache(
            db_stale,
            symbols=["BTCUSDT"],
            category="linear",
            lookback_hours=8,
            now=now,
        )
        == {}
    )
    out = _bulk_load_funding_avg_from_cache(
        db_fresh,
        symbols=["BTCUSDT"],
        category="linear",
        lookback_hours=8,
        now=now,
    )
    assert out["BTCUSDT"] == pytest.approx(0.0002)


def test_enrich_derivative_metrics_uses_cache_and_skips_api():
    now = datetime.now(timezone.utc)
    db = _FakeDB(
        {
            "funding": [("ETHUSDT", 0.0001, now - timedelta(hours=1))],
            "oi": [("ETHUSDT", 5_000_000.0)],
            "lsr": [("ETHUSDT", 0.6, 0.4)],
        }
    )
    client = MagicMock()
    client.get_funding_history = AsyncMock()
    client.get_open_interest = AsyncMock()
    client.get_account_ratio = AsyncMock()
    client.get_tickers = AsyncMock()

    row = ScreeningRow(
        symbol="ETHUSDT",
        turnover24h=1e8,
        lastPrice=3000.0,
        spreadPercent=0.06,
        score=1.0,
    )
    filters = CryptoUniverseFilters(
        min_funding_rate=-0.001,
        max_funding_rate=0.001,
        min_open_interest_usd=1.0,
        min_lsr=0.1,
        max_lsr=5.0,
        funding_lookback_hours=8,
    )
    stats = asyncio.run(
        enrich_derivative_metrics_live(client, [row], filters=filters, db=db)
    )
    assert stats["funding_cache_hits"] == 1
    assert stats["oi_cache_hits"] == 1
    assert stats["lsr_cache_hits"] == 1
    assert stats["funding_api"] == 0
    assert stats["oi_api"] == 0
    assert stats["lsr_api"] == 0
    client.get_funding_history.assert_not_called()
    client.get_open_interest.assert_not_called()
    client.get_account_ratio.assert_not_called()
    assert row.avg_funding_rate == pytest.approx(0.0001)
    assert row.open_interest_usd == pytest.approx(5_000_000.0)
    assert row.lsr == pytest.approx(1.5)


def test_enrich_derivative_metrics_api_on_cache_miss():
    db = _FakeDB({})
    client = MagicMock()
    client.get_funding_history = AsyncMock(
        return_value={
            "result": {
                "list": [
                    {
                        "fundingRate": "0.0002",
                        "fundingRateTimestamp": str(
                            int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp() * 1000)
                        ),
                    }
                ]
            }
        }
    )
    client.get_open_interest = AsyncMock(
        return_value={"result": {"list": [{"openInterest": "10", "markPrice": "100"}]}}
    )
    client.get_account_ratio = AsyncMock(
        return_value={"result": {"list": [{"buyRatio": "0.5", "sellRatio": "0.5"}]}}
    )
    client.get_tickers = AsyncMock()

    row = ScreeningRow(
        symbol="SOLUSDT",
        turnover24h=1e8,
        lastPrice=100.0,
        spreadPercent=0.2,
        score=1.0,
    )
    filters = CryptoUniverseFilters(funding_lookback_hours=8)
    stats = asyncio.run(
        enrich_derivative_metrics_live(client, [row], filters=filters, db=db)
    )
    assert stats["funding_api"] == 1
    assert stats["oi_api"] == 1
    assert stats["lsr_api"] == 1
    assert stats["funding_cache_hits"] == 0
    assert stats["cache_commits"] == 1
    assert db.commits == 1
    client.get_funding_history.assert_awaited()
    client.get_open_interest.assert_awaited()
    client.get_account_ratio.assert_awaited()
    assert row.open_interest_usd == pytest.approx(1000.0)  # 10 * 100
    assert any("INSERT" in sql.upper() and "bybit_funding_history" in sql for sql, _ in db.executed)
    assert any("INSERT" in sql.upper() and "bybit_open_interest_history" in sql for sql, _ in db.executed)
    assert any("INSERT" in sql.upper() and "bybit_lsr_history" in sql for sql, _ in db.executed)


def test_enrich_cache_hit_does_not_commit():
    now = datetime.now(timezone.utc)
    db = _FakeDB(
        {
            "funding": [("ETHUSDT", 0.0001, now - timedelta(hours=1))],
            "oi": [("ETHUSDT", 5_000_000.0)],
            "lsr": [("ETHUSDT", 0.6, 0.4)],
        }
    )
    client = MagicMock()
    row = ScreeningRow(
        symbol="ETHUSDT",
        turnover24h=1e8,
        lastPrice=3000.0,
        spreadPercent=0.06,
        score=1.0,
    )
    filters = CryptoUniverseFilters(
        min_funding_rate=-0.001,
        max_funding_rate=0.001,
        min_open_interest_usd=1.0,
        min_lsr=0.1,
        max_lsr=5.0,
        funding_lookback_hours=8,
    )
    stats = asyncio.run(
        enrich_derivative_metrics_live(client, [row], filters=filters, db=db)
    )
    assert stats["cache_commits"] == 0
    assert db.commits == 0
