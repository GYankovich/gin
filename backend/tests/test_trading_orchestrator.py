"""TradingOrchestrator — этап 3 BRD-ARCH-04."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.robots.trading.runtime import (
    TradingOrchestrator,
    build_allowed_figis_by_date,
    build_allowed_symbols_by_date,
    get_trading_orchestrator,
)
from app.modules.robots.trading.backtest.types import BacktestResult


def _one_candle():
    t = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)
    q = {"units": 100, "nano": 0}
    return {
        "time": t.isoformat().replace("+00:00", "Z"),
        "open": q,
        "high": q,
        "low": q,
        "close": q,
        "volume": 100,
    }


def test_get_trading_orchestrator_singleton():
    assert get_trading_orchestrator() is get_trading_orchestrator()


def test_build_allowed_figis_by_date():
    c = _one_candle()
    m = build_allowed_figis_by_date({"SBER": [c], "GAZP": [c]})
    assert "2024-06-01" in m
    assert "SBER" in m["2024-06-01"]
    assert "GAZP" in m["2024-06-01"]


def test_build_allowed_symbols_by_date_alias():
    c = _one_candle()
    m = build_allowed_symbols_by_date({"BTCUSDT": [c]})
    assert "2024-06-01" in m
    assert "BTCUSDT" in m["2024-06-01"]


def test_prefetch_crypto_candles_for_replay(monkeypatch):
    import asyncio
    from datetime import date
    from unittest.mock import MagicMock

    from app.modules.robots.trading.data.stats import CandlePrefetchStats
    from app.modules.robots.trading.intervals import resolve_strategy_interval

    class _FakeOrch(TradingOrchestrator):
        def load_candles_by_symbol_from_cache(self, db, **kwargs):
            return {
                "BTCUSDT": [
                    {
                        "time": "2024-06-01T10:00:00+00:00",
                        "open": {"units": 100, "nano": 0},
                        "high": {"units": 110, "nano": 0},
                        "low": {"units": 90, "nano": 0},
                        "close": {"units": 105, "nano": 0},
                        "volume": 10,
                    }
                ]
            }

    async def _fake_ensure(*args, **kwargs):
        return CandlePrefetchStats(total_tickers=1, fetched_tickers=1, fetched_candles=2)

    monkeypatch.setattr(
        "app.modules.robots.trading.data.providers.bybit_market.ensure_candles_bybit_market",
        _fake_ensure,
    )
    resolved = resolve_strategy_interval("CANDLE_INTERVAL_5_MIN")

    async def _run():
        stats, candles = await _FakeOrch().prefetch_crypto_candles_for_replay(
            MagicMock(),
            symbols=["BTCUSDT"],
            resolved=resolved,
            from_date=date(2024, 6, 1),
            till_date=date(2024, 6, 2),
            testnet=True,
        )
        return stats, candles

    stats, candles = asyncio.run(_run())
    assert stats.fetched_candles == 2
    assert candles == {}


def test_prefetch_crypto_candles_for_replay_load_cached_candles(monkeypatch):
    import asyncio
    from datetime import date
    from unittest.mock import MagicMock

    from app.modules.robots.trading.data.stats import CandlePrefetchStats
    from app.modules.robots.trading.intervals import resolve_strategy_interval

    class _FakeOrch(TradingOrchestrator):
        def load_candles_by_symbol_from_cache(self, db, **kwargs):
            return {
                "BTCUSDT": [
                    {
                        "time": "2024-06-01T10:00:00+00:00",
                        "open": {"units": 100, "nano": 0},
                        "high": {"units": 110, "nano": 0},
                        "low": {"units": 90, "nano": 0},
                        "close": {"units": 105, "nano": 0},
                        "volume": 10,
                    }
                ]
            }

    async def _fake_ensure(*args, **kwargs):
        return CandlePrefetchStats(total_tickers=1, fetched_tickers=1, fetched_candles=2)

    monkeypatch.setattr(
        "app.modules.robots.trading.data.providers.bybit_market.ensure_candles_bybit_market",
        _fake_ensure,
    )
    resolved = resolve_strategy_interval("CANDLE_INTERVAL_5_MIN")

    async def _run():
        stats, candles = await _FakeOrch().prefetch_crypto_candles_for_replay(
            MagicMock(),
            symbols=["BTCUSDT"],
            resolved=resolved,
            from_date=date(2024, 6, 1),
            till_date=date(2024, 6, 2),
            testnet=True,
            load_cached_candles=True,
        )
        return stats, candles

    stats, candles = asyncio.run(_run())
    assert stats.fetched_candles == 2
    assert "BTCUSDT" in candles
    assert candles["BTCUSDT"][0]["close"]["units"] == 105


def test_run_backtest_replay_delegates_to_session():
    import asyncio

    expected = BacktestResult(
        initial_capital=1_000_000.0,
        final_equity=1_010_000.0,
        total_return_percent=1.0,
        max_drawdown_percent=None,
    )
    mock_session = MagicMock()
    mock_session.run_history_replay = AsyncMock(return_value=expected)

    orch = TradingOrchestrator()
    with patch(
        "app.modules.robots.trading.runtime.orchestrator.create_trading_session",
        return_value=mock_session,
    ):
        with patch(
            "app.modules.robots.trading.runtime.orchestrator.SimBacktestBrokerFacade",
            return_value=MagicMock(),
        ):
            res = asyncio.run(
                orch.run_backtest_replay(
                    db=MagicMock(),
                    schema="ganaly",
                    robot_id=10,
                    user_id=1,
                    token_id=0,
                    token="",
                    config={"strategy": "momentum_breakout", "strategy_params": {}, "risk": {}},
                    candles_by_figi={"SBER": [_one_candle()]},
                    allowed_figis_by_date={"2024-06-01": ["SBER"]},
                    initial_capital=1_000_000.0,
                )
            )
    assert res is expected
    mock_session.run_history_replay.assert_awaited_once()
