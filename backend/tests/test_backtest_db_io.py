"""Backtest I/O: no DB persist on replay, no refresh_config DB round-trips."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.robots.trading.contracts import ExecutionMode
from app.modules.robots.trading.core.trading_core import run_single_trading_cycle
from app.modules.robots.trading.indicators.service import IndicatorService
from app.modules.robots.trading.session_backtest import BacktestTradingSession


def test_on_closed_candle_skips_db_when_persist_false():
    svc = IndicatorService()
    broker = MagicMock()
    broker.cache_namespace = "sim"

    async def _run():
        with patch("app.modules.robots.trading.indicators.service.SessionLocal") as mock_sl:
            await svc.on_closed_candle(
                1,
                broker,
                "BTCUSDT",
                {"time": "2024-06-01T10:00:00+00:00", "close": {"units": 1, "nano": 0}},
                {"interval": "CANDLE_INTERVAL_5_MIN", "candle_days": 7},
                persist_to_db=False,
            )
            mock_sl.assert_not_called()

    asyncio.run(_run())


def test_backtest_refresh_config_is_noop():
    session = BacktestTradingSession(
        sim_broker=MagicMock(),
        allowed_figis_by_date={},
        db=MagicMock(),
        schema="ganaly",
        robot_id=1,
        user_id=1,
        token_id=0,
        token="",
        config={"strategy": "reversion_to_ma"},
    )

    async def _run():
        await session.refresh_config()
        session.db.execute.assert_not_called()

    asyncio.run(_run())


def test_trading_cycle_skips_db_rollback_in_backtest():
    host = MagicMock()
    host.mode = ExecutionMode.BACKTEST
    host.db = MagicMock()
    host._now.return_value = MagicMock()
    host._reset_cycle_api_counts = MagicMock()
    host.create_run_cycle = AsyncMock(return_value=None)
    host._write_log = MagicMock()
    host.refresh_config = AsyncMock()
    host._refresh_account_positions = AsyncMock()
    host.strategy_name = "reversion_to_ma"
    host._get_latest_prices_from_queue = AsyncMock(return_value={})
    host.price_queue = MagicMock()
    host.price_queue.qsize.return_value = 0
    host._process_order_statuses = AsyncMock()
    host._skip_cycle_sleep = True
    host.update_interval = 0
    host.stats = {"signals_generated": 0, "orders_placed": 0}

    async def _run():
        await run_single_trading_cycle(host, 1)
        host.db.rollback.assert_not_called()

    asyncio.run(_run())
