from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from app.core.logging_config import (
    _ChannelSlotFileHandler,
    _RobotSlotFileHandler,
    get_robot_logger,
)
from app.core.robot_logging import APILogger, _broker_from_endpoint


def test_broker_from_endpoint():
    assert _broker_from_endpoint("bybit.get_accounts", "portfolio_updater") == "bybit"
    assert _broker_from_endpoint("tinvest.get_portfolio", "portfolio_updater") == "tinvest"
    assert _broker_from_endpoint("https://api.bybit.com/v5/account/wallet-balance", "x") == "bybit"


def test_robot_log_path_layout(tmp_path: Path, monkeypatch):
    import app.core.logging_config as lc

    monkeypatch.setattr(lc, "_LOG_ROOT", tmp_path)
    adapter = get_robot_logger("robots.portfolio_updater", 24)
    adapter.info("hello slot log")

    day, h_start, h_end = lc._slot_now()
    expected = (
        tmp_path
        / day
        / "robots"
        / "portfolio_updater_robot"
        / f"id_24_{h_start:02d}-{h_end:02d}.log"
    )
    assert expected.exists(), f"missing {expected}"
    content = expected.read_text(encoding="utf-8")
    assert "hello slot log" in content
    assert any(isinstance(h, _RobotSlotFileHandler) for h in adapter.logger.handlers)


def test_app_rest_errors_channel_layout(tmp_path: Path, monkeypatch):
    import app.core.logging_config as lc

    monkeypatch.setattr(lc, "_LOG_ROOT", tmp_path)
    # Avoid wiping unrelated loggers in the test process more than needed:
    # call channel handlers directly like setup_logging does.
    day, h_start, h_end = lc._slot_now()
    fmt = logging.Formatter("%(message)s")
    for channel in ("app", "rest", "errors"):
        handler = _ChannelSlotFileHandler(tmp_path, channel, logging.DEBUG, fmt)
        logger = logging.getLogger(f"test.channel.{channel}")
        logger.handlers.clear()
        logger.propagate = False
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.info("msg-%s", channel)
        expected = tmp_path / day / channel / f"{h_start:02d}-{h_end:02d}.log"
        assert expected.exists(), f"missing {expected}"
        assert f"msg-{channel}" in expected.read_text(encoding="utf-8")
        handler.close()
        logger.removeHandler(handler)


def test_api_logger_writes_external_api_logs():
    executed = {}

    class _Result:
        def first(self):
            return (99,)

    db = MagicMock()

    def execute(query, params=None):
        q = str(query)
        executed.setdefault("queries", []).append(q)
        executed["last_params"] = params
        if "RETURNING id" in q:
            return _Result()
        return MagicMock()

    db.execute.side_effect = execute

    logger = APILogger(
        db=db,
        schema="ganaly",
        robot_type="portfolio_updater",
        robot_name="tinvest",
        robot_version="2.1.0",
        execution_log_id=7,
        robot_id=42,
        write_external_api_logs=True,
        write_robot_logs=False,
    )

    async def _run():
        return await logger.log(
            endpoint="bybit.get_accounts",
            request_data={},
            response_data={"accounts_count": 3},
            response_status=200,
            token_id=5,
            user_id=1,
            started_at=datetime.now(timezone.utc),
        )

    result = asyncio.run(_run())
    assert result is None
    assert any("external_api_logs" in q for q in executed["queries"])
    params = executed["last_params"]
    assert params["broker"] == "bybit"
    assert params["context_type"] == "portfolio_updater"
    assert params["context_ref"] == "42"
    assert params["endpoint"] == "bybit.get_accounts"
    assert params["success"] == 1
    assert json.loads(params["response_data"])["accounts_count"] == 3
