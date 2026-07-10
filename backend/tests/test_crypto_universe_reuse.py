from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.modules.robots.crypto_universe import (
    rebuild_crypto_universe,
    try_reuse_fresh_crypto_universe,
)


class _FakeResult:
    def __init__(self, rows=None, first=None):
        self._rows = rows or []
        self._first = first

    def fetchall(self):
        return self._rows

    def first(self):
        if self._first is not None:
            return self._first
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, *, max_created_at, accepted_symbols):
        self.max_created_at = max_created_at
        self.accepted_symbols = accepted_symbols
        self.executed = []
        self.commits = 0

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append((sql, params or {}))
        if "MAX(created_at)" in sql:
            return _FakeResult(first=(self.max_created_at,))
        if "filter_result" in sql and "accepted" in sql.lower():
            return _FakeResult([(s,) for s in self.accepted_symbols])
        return _FakeResult([])

    def commit(self):
        self.commits += 1


def test_try_reuse_fresh_crypto_universe_within_ttl():
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    db = _FakeDB(
        max_created_at=now - timedelta(minutes=20),
        accepted_symbols=["BTCUSDT", "ETHUSDT"],
    )
    cfg = {
        "crypto_universe": {
            "refresh": {"every_minutes": 60},
            "last_screened_at": (now - timedelta(minutes=20)).isoformat(),
            "stats": {"scanned": 400, "rejected": 350},
        }
    }
    out = try_reuse_fresh_crypto_universe(db, robot_id=24, config=cfg, now=now)
    assert out is not None
    assert out["reused"] is True
    assert out["skipped"] is False
    assert out["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert out["accepted"] == 2


def test_try_reuse_fresh_crypto_universe_expired():
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    db = _FakeDB(
        max_created_at=now - timedelta(minutes=90),
        accepted_symbols=["BTCUSDT"],
    )
    cfg = {
        "crypto_universe": {
            "refresh": {"every_minutes": 60},
            "last_screened_at": (now - timedelta(minutes=90)).isoformat(),
        }
    }
    assert try_reuse_fresh_crypto_universe(db, robot_id=24, config=cfg, now=now) is None


def test_rebuild_reuses_without_http(monkeypatch):
    now = datetime.now(timezone.utc)
    db = _FakeDB(
        max_created_at=now - timedelta(minutes=5),
        accepted_symbols=["SOLUSDT"],
    )
    cfg = {
        "allowed_symbols": ["OLD"],
        "crypto_universe": {
            "refresh": {"every_minutes": 60},
            "last_screened_at": (now - timedelta(minutes=5)).isoformat(),
        },
    }

    async def _should_not_fetch(**kwargs):
        raise AssertionError("fetch_bybit_tickers must not be called on reuse")

    monkeypatch.setattr(
        "app.modules.robots.crypto_universe._find_active_bybit_token",
        lambda *a, **k: {"token": "k", "token_secret": "s"},
    )
    monkeypatch.setattr(
        "app.modules.robots.crypto_universe.fetch_bybit_tickers",
        _should_not_fetch,
    )

    result = asyncio.run(
        rebuild_crypto_universe(db, robot_id=24, user_id=1, config=cfg, force=False)
    )
    assert result["reused"] is True
    assert result["symbols"] == ["SOLUSDT"]
    assert cfg["allowed_symbols"] == ["SOLUSDT"]


def test_rebuild_force_bypasses_reuse(monkeypatch):
    now = datetime.now(timezone.utc)
    db = _FakeDB(
        max_created_at=now - timedelta(minutes=1),
        accepted_symbols=["BTCUSDT"],
    )
    # Make execute also handle DELETE/INSERT/UPDATE for full rebuild path
    real_execute = db.execute

    def execute(stmt, params=None):
        sql = str(stmt)
        if "UPDATE" in sql.upper() and "robots" in sql:
            db.executed.append((sql, params or {}))
            return _FakeResult([])
        if "DELETE" in sql.upper() or "INSERT" in sql.upper():
            db.executed.append((sql, params or {}))
            return _FakeResult([])
        return real_execute(stmt, params)

    db.execute = execute

    cfg = {
        "crypto_universe": {
            "refresh": {"every_minutes": 60},
            "last_screened_at": now.isoformat(),
            "min_funding_rate": None,
            "max_funding_rate": None,
            "min_open_interest_usd": None,
            "min_lsr": None,
            "max_lsr": None,
            "min_rvol": None,
            "min_atr_percent": None,
            "max_atr_percent": None,
            "min_turnover_24h_usd": 1_000_000,
            "max_spread_pct": 0.5,
        }
    }

    async def _fake_fetch(**kwargs):
        return [
            {
                "symbol": "BTCUSDT",
                "turnover24h": "9000000",
                "lastPrice": "68000",
                "bid1Price": "67990",
                "ask1Price": "68000",
            }
        ]

    class _Client:
        async def close(self):
            return None

    monkeypatch.setattr(
        "app.modules.robots.crypto_universe._find_active_bybit_token",
        lambda *a, **k: {"token": "k", "token_secret": "s"},
    )
    monkeypatch.setattr(
        "app.modules.robots.crypto_universe.fetch_bybit_tickers",
        _fake_fetch,
    )
    monkeypatch.setattr(
        "app.modules.robots.crypto_universe.BybitHttpClient",
        lambda **kwargs: _Client(),
    )

    result = asyncio.run(
        rebuild_crypto_universe(db, robot_id=24, user_id=1, config=cfg, force=True)
    )
    assert result["reused"] is False
    assert result["symbols"] == ["BTCUSDT"]
