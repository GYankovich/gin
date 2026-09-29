"""Orphan LIMIT cancel + reconcile fail streak halt."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots.trading.contracts import OrderIntent
from app.modules.robots_v2.engine.execution import ExecutionService, RestingOrder
from app.modules.robots_v2.engine.paper_ledger import PaperLedger
from app.modules.robots_v2.engine.resting_orphans import select_orphan_resting_tickers


def test_select_orphan_exit_without_position():
    resting = {
        "SBER": RestingOrder(
            intent_id="1",
            ticker="SBER",
            side="SELL",
            quantity=10,
            limit_price=300.0,
            reduce_only=True,
            reason="take_profit",
            kind="exit_sl_tp",
        ),
    }
    orphans = select_orphan_resting_tickers(
        resting,
        held_tickers=set(),
        wanted_entries=set(),
        scope="exit",
    )
    assert orphans == ["SBER"]


def test_select_orphan_entry_without_signal():
    resting = {
        "GAZP": RestingOrder(
            intent_id="2",
            ticker="GAZP",
            side="BUY",
            quantity=5,
            limit_price=150.0,
            reduce_only=False,
            reason="entry",
            kind="entry",
        ),
    }
    orphans = select_orphan_resting_tickers(
        resting,
        held_tickers=set(),
        wanted_entries=set(),
        scope="entry",
    )
    assert orphans == ["GAZP"]
    kept = select_orphan_resting_tickers(
        resting,
        held_tickers=set(),
        wanted_entries={("GAZP", "BUY")},
        scope="entry",
    )
    assert kept == []


def test_cancel_resting_keeps_tracking_on_broker_failure():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=1,
        ledger=ledger,
        account_id="acc-1",
        instrument_map={"SBER": "BBG004730N88"},
    )
    exec_svc._resting["SBER"] = RestingOrder(
        intent_id="oid",
        ticker="SBER",
        side="SELL",
        quantity=10,
        limit_price=300.0,
        reduce_only=True,
        reason="take_profit",
        kind="exit_sl_tp",
        broker_order_id="broker-1",
    )

    class _Broker:
        broker_type = "tinvest"

        async def cancel_order(self, account_id, order_id):
            raise RuntimeError("broker down")

    exec_svc.broker = _Broker()  # type: ignore[assignment]

    ok = asyncio.run(exec_svc.cancel_resting("SBER"))
    assert ok is False
    assert "SBER" in exec_svc._resting
    assert exec_svc._resting["SBER"].broker_order_id == "broker-1"


def test_cancel_resting_clears_on_success():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=1,
        ledger=ledger,
        account_id="acc-1",
        instrument_map={"SBER": "BBG004730N88"},
    )
    exec_svc._resting["SBER"] = RestingOrder(
        intent_id="oid",
        ticker="SBER",
        side="SELL",
        quantity=10,
        limit_price=300.0,
        reduce_only=True,
        reason="take_profit",
        kind="exit_sl_tp",
        broker_order_id="broker-1",
    )
    cancelled: list[str] = []

    class _Broker:
        broker_type = "tinvest"

        async def cancel_order(self, account_id, order_id):
            cancelled.append(order_id)

    exec_svc.broker = _Broker()  # type: ignore[assignment]
    ok = asyncio.run(exec_svc.cancel_resting("SBER"))
    assert ok is True
    assert "SBER" not in exec_svc._resting
    assert cancelled == ["broker-1"]


def test_market_exit_strategy_clears_resting():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    ledger.apply_fill(ticker="SBER", side="BUY", quantity=10, price=100.0)
    exec_svc = ExecutionService(mode="paper", robot_id=1, ledger=ledger, slippage_pct=0)
    limit_intent = OrderIntent(
        kind="exit_sl_tp",
        figi="SBER",
        side="SELL",
        quantity=10,
        price=110.0,
        order_type="LIMIT",
        reduce_only=True,
        reason="take_profit",
    )
    close_intent = OrderIntent(
        kind="exit_strategy",
        figi="SBER",
        side="SELL",
        quantity=10,
        price=105.0,
        order_type="MARKET",
        reduce_only=True,
        reason="signal_close",
    )

    async def _run():
        await exec_svc.execute_intent(limit_intent, last_price=105.0)
        assert "SBER" in exec_svc._resting
        return await exec_svc.execute_intent(close_intent, last_price=105.0)

    result = asyncio.run(_run())
    assert result.status == "filled"
    assert "SBER" not in exec_svc._resting


def test_reconcile_fail_streak_halts_risk():
    from app.modules.robots_v2.engine.session import TradingSessionV2
    from app.modules.robots_v2.risk.engine import SessionRiskState

    session = TradingSessionV2(
        robot_id=99,
        user_id=1,
        token_id=None,
        config={"configVersion": 4},
        virtual_capital=100_000,
        stop_mode="soft",
    )
    state = SessionRiskState()

    class _Risk:
        session_state = state

        def halt(self, reason: str) -> None:
            state.accept_new_entries = False
            state.halt_session = True
            state.halt_reason = reason

    session.risk = _Risk()  # type: ignore[assignment]
    session._reconcile_fail_halt_after = 3

    assert session._note_reconcile_outcome(False, error="net") is False
    assert session._note_reconcile_outcome(False, error="net") is False
    assert state.halt_session is False
    assert session._note_reconcile_outcome(False, error="net") is True
    assert state.halt_session is True
    assert state.halt_reason == "RECONCILE_FAILED"

    assert session._note_reconcile_outcome(True) is False
    assert session._reconcile_fail_streak == 0
    assert state.halt_session is True  # halt sticky until restart
