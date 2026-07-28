"""LiveExecutionService — этап 4 BRD-ARCH-04."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.robots.trading.execution import (
    LiveExecutionService,
    build_live_execution_service,
    execution_service_for_session,
)


def test_submit_signals_empty():
    import asyncio

    svc = build_live_execution_service(
        db=MagicMock(),
        schema="ganaly",
        broker=MagicMock(),
        account_id="acc",
        robot_id=1,
        token_id=2,
        user_id=3,
    )
    assert asyncio.run(svc.submit_signals([])) == []


def test_submit_signals_delegates_to_stage6():
    import asyncio

    svc = build_live_execution_service(
        db=MagicMock(),
        schema="ganaly",
        broker=MagicMock(),
        account_id="acc",
        robot_id=1,
        token_id=2,
        user_id=3,
    )
    expected = [{"figi": "SBER", "status": "open", "order_id": "oid-1"}]
    with patch(
        "app.modules.robots.trading.execution.service.Stage6Orders.execute_signals",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_exec:
        out = asyncio.run(
            svc.submit_signals(
                [{"figi": "SBER", "signal": "BUY", "quantity": 1, "price": 100.0}],
                risk_params={"max_trades_per_day": 10},
            )
        )
    mock_exec.assert_awaited_once()
    assert out == expected


def test_execution_service_for_session_reads_broker_type():
    session = MagicMock()
    session.db = MagicMock()
    session.schema = "ganaly"
    session.broker = MagicMock()
    session.account_id = "A"
    session.robot_id = 10
    session.token_id = 5
    session.user_id = 1
    session._write_log = MagicMock()
    session._daily_trade_counter = {}
    session._last_trade_by_figi = {}
    session.cost_params = None
    session.account_positions = {}
    session._now = MagicMock()
    session.config = {"broker_type": "tinvest"}
    session.broker_type = "tinvest"

    svc = execution_service_for_session(session)
    assert svc.broker_type == "tinvest"
    assert isinstance(svc, LiveExecutionService)
