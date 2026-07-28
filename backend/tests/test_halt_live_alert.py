"""HALT → Live UI error alert wiring (unit-level)."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robots.trading.session import TradingSession


def test_halt_trading_publishes_error_alert_and_stops():
    session = TradingSession.__new__(TradingSession)
    session._trading_halted = False
    session._trading_halt_reason = None
    session.robot_id = 24
    session.db = None
    session.running = True
    session._write_log = MagicMock()
    session._publish_live_event = AsyncMock()

    with patch("app.modules.robots.trading.session.notify_live_alert") as alert:
        asyncio.run(session._halt_trading("margin_health: mm_rate>=0.80"))

    assert session._trading_halted is True
    assert session.running is False
    assert "mm_rate" in session._trading_halt_reason
    session._write_log.assert_called()
    assert session._publish_live_event.await_count >= 1
    err_payload = session._publish_live_event.await_args_list[0].args[0]
    assert err_payload["type"] == "log"
    assert err_payload["level"] == "ERROR"
    alert.assert_called_once()
    assert str(alert.call_args.args[1]).startswith("HALT:")
