from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.modules.robots.crypto_universe import CryptoUniverseFilters, rebuild_crypto_universe, score_bybit_tickers


def test_score_bybit_tickers_filters_volume_and_spread():
    rows = [
        {"symbol": "BTCUSDT", "turnover24h": "9000000", "lastPrice": "68000", "bid1Price": "67990", "ask1Price": "68000"},
        {"symbol": "ETHUSDT", "turnover24h": "500000", "lastPrice": "3500", "bid1Price": "3499", "ask1Price": "3501"},
        {"symbol": "DOGEUSDT", "turnover24h": "5000000", "lastPrice": "0.15", "bid1Price": "0.10", "ask1Price": "0.20"},
    ]
    out = score_bybit_tickers(rows, filters=CryptoUniverseFilters(min_turnover_24h_usd=1_000_000, max_spread_pct=0.3))
    assert [x["symbol"] for x in out] == ["BTCUSDT"]


def test_rebuild_crypto_universe_updates_allowed_symbols(monkeypatch):
    class _DB:
        def __init__(self):
            self.executed = []
            self.commits = 0

        def execute(self, stmt, params):
            self.executed.append((str(stmt), params))
            return SimpleNamespace(first=lambda: None, fetchall=lambda: [])

        def commit(self):
            self.commits += 1

    async def _fake_fetch(**kwargs):
        _ = kwargs
        return [
            {"symbol": "BTCUSDT", "turnover24h": "9000000", "lastPrice": "68000", "bid1Price": "67990", "ask1Price": "68000"},
            {"symbol": "XRPUSDT", "turnover24h": "4500000", "lastPrice": "0.5", "bid1Price": "0.49", "ask1Price": "0.51"},
        ]

    monkeypatch.setattr("app.modules.robots.crypto_universe._find_active_bybit_token", lambda db, user_id: {"token": "k", "token_secret": "s", "testnet": True})
    monkeypatch.setattr("app.modules.robots.crypto_universe.fetch_bybit_tickers", _fake_fetch)

    db = _DB()
    cfg = {
        "crypto_universe": {
            "max_spread_pct": 0.2,
            "min_turnover_24h_usd": 1_000_000,
            "quote_coin": "USDT",
            # Disable live derivative/volatility stages (would hit ByBit HTTP).
            "min_funding_rate": None,
            "max_funding_rate": None,
            "min_open_interest_usd": None,
            "min_lsr": None,
            "max_lsr": None,
            "min_rvol": None,
            "min_atr_percent": None,
            "max_atr_percent": None,
        }
    }
    result = asyncio.run(rebuild_crypto_universe(db, robot_id=7, user_id=12, config=cfg))
    assert result["accepted"] == 1
    assert result["symbols"] == ["BTCUSDT"]
    assert cfg["allowed_symbols"] == ["BTCUSDT"]
    assert db.commits == 1
    executed_sql = "\n".join(sql for sql, _ in db.executed)
    assert "crypto_universe_daily" in executed_sql

