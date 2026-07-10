"""Trading core — smoke tests (BRD-ARCH-04 этап 1)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.modules.robots.trading.core import TradingCore, run_single_trading_cycle


def test_run_single_trading_cycle_no_prices_skips_signal_path():
    host = MagicMock()
    host.db = None
    host._now.return_value = datetime.now(timezone.utc)
    host._reset_cycle_api_counts = MagicMock()
    host.create_run_cycle = AsyncMock(return_value=1)
    host._write_log = MagicMock()
    host.refresh_config = AsyncMock()
    host._refresh_account_positions = AsyncMock()
    host.strategy_name = "momentum_breakout"
    host.strategy_params = {}
    host.broker_type = "tinvest"
    host.robot_id = 10
    host.schema = "ganaly"
    host._execution_log_id = None
    host.price_queue = MagicMock()
    host.price_queue.qsize.return_value = 0
    host._get_latest_prices_from_queue = AsyncMock(return_value={})
    host._process_order_statuses = AsyncMock()
    host._skip_cycle_sleep = True
    host.update_interval = 60

    asyncio.run(run_single_trading_cycle(host, 1))

    host._generate_signals.assert_not_called()
    host._execute_orders.assert_not_called()
    host._process_order_statuses.assert_awaited_once()


def test_trading_core_class_delegates():
    core = TradingCore()
    assert hasattr(core, "run_cycle")
