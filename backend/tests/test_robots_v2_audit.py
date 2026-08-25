"""Unit tests for robots v2 audit trail."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.modules.robots_v2.engine.audit import (
    AuditCycleBundle,
    AuditDecisionRow,
    AuditExecutionRow,
    AuditSignalRow,
    AuditStore,
    audit_end_session,
    audit_persist_cycle,
    decision_row_from_dict,
    execution_row_from_result,
    signal_row_from_eval,
)


class _FakeResult:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_decision_row_from_dict_deny():
    row = decision_row_from_dict({
        "code": "MAX_POSITIONS",
        "message": "limit reached",
        "ticker": "sber",
        "allow": False,
        "qty": 10,
    })
    assert row.outcome == "deny"
    assert row.code == "MAX_POSITIONS"
    assert row.ticker == "SBER"
    assert row.context.get("qty") == 10


def test_decision_row_from_dict_skip_no_signal():
    row = decision_row_from_dict({
        "code": "NO_SIGNAL",
        "message": "quiet",
        "allow": True,
    }, stage="strategy")
    assert row.outcome == "skip"
    assert row.stage == "strategy"


def test_decision_row_from_dict_allow():
    row = decision_row_from_dict({"code": "OK", "allow": True})
    assert row.outcome == "allow"


def test_execution_row_from_result_fill():
    result = _FakeResult(
        ticker="GAZP",
        side="buy",
        quantity=10,
        price=165.5,
        status="filled",
        mode="live",
        pnl=42.0,
        broker_order_id="ord-1",
        kind="entry",
    )
    row = execution_row_from_result(result, kind="entry")
    assert row.ticker == "GAZP"
    assert row.side == "BUY"
    assert row.status == "filled"
    assert row.broker_order_id == "ord-1"
    assert row.reject_reason is None


def test_execution_row_from_result_rejected():
    result = _FakeResult(
        ticker="LKOH",
        side="SELL",
        quantity=1,
        price=7000,
        status="rejected",
        mode="live",
        reason="IN_FLIGHT_ORDER",
        kind="entry",
    )
    row = execution_row_from_result(result)
    assert row.reject_reason == "IN_FLIGHT_ORDER"


def test_signal_row_from_eval_close_includes_entry_and_delta():
    class _Pos:
        quantity = 10
        avg_entry_price = 1198.2

    class _Flow:
        delta_pct = -6.5

    class _Sig:
        secid = "PLZL"
        side = "CLOSE"
        reason = "scalper_delta_reversal"
        price_at_signal = 1199.2

    row = signal_row_from_eval(
        _Sig(),
        prices={"PLZL": 1199.0},
        positions={"PLZL": _Pos()},
        order_flow={"PLZL": _Flow()},
    )
    assert row.ticker == "PLZL"
    assert row.side == "CLOSE"
    assert row.entry_price == 1198.2
    assert row.delta_pct == -6.5
    assert row.price == 1199.2


def test_signal_row_from_eval_buy_flat_has_no_entry():
    class _Flow:
        delta_pct = 7.2

    class _Sig:
        secid = "SBER"
        side = "BUY"
        reason = "scalper_delta_cross"
        price_at_signal = 250.0

    row = signal_row_from_eval(
        _Sig(),
        prices={"SBER": 250.0},
        positions={},
        order_flow={"SBER": _Flow()},
    )
    assert row.entry_price is None
    assert row.delta_pct == 7.2


def test_audit_store_persist_cycle_inserts():
    db = MagicMock()
    store = AuditStore(db=db)
    sid = uuid4()
    cid = uuid4()
    bundle = AuditCycleBundle(
        cycle_id=cid,
        session_id=sid,
        robot_id=1,
        cycle_number=3,
        triggered_by="poll",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        status="ok",
        equity=10_000.0,
        stats={"signals": 1},
        signals=[
            AuditSignalRow(
                ticker="SBER",
                side="CLOSE",
                kind="signal",
                reason="scalper_delta_reversal",
                price=250.5,
                entry_price=251.0,
                delta_pct=-5.5,
            ),
        ],
        decisions=[
            AuditDecisionRow(
                stage="risk",
                outcome="deny",
                code="MAX_POSITIONS",
                message="denied",
                ticker="SBER",
            ),
        ],
        executions=[
            AuditExecutionRow(
                ticker="SBER",
                side="BUY",
                kind="entry",
                quantity=10,
                price=250.0,
                status="filled",
                mode="paper",
                pnl=0.0,
            ),
        ],
    )
    store.persist_cycle(bundle)
    assert db.execute.call_count >= 3
    db.commit.assert_called_once()
    store.close()


def test_audit_store_start_and_end_session():
    db = MagicMock()
    store = AuditStore(db=db)
    sid = store.start_session(
        robot_id=7,
        mode="paper",
        virtual_capital=5000,
        account_id=None,
    )
    assert sid is not None
    store.end_session(sid, stop_reason="soft_stop")
    assert db.execute.call_count == 2
    assert db.commit.call_count == 2


def test_audit_end_session_noop_when_none():
    asyncio.run(audit_end_session(None, stop_reason="soft_stop"))


def test_audit_persist_cycle_swallows_db_errors():
    bundle = AuditCycleBundle(
        cycle_id=uuid4(),
        session_id=uuid4(),
        robot_id=1,
        cycle_number=1,
        triggered_by="poll",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )

    with patch("app.modules.robots_v2.engine.audit.AuditStore") as mock_cls:
        mock_cls.return_value.persist_cycle.side_effect = RuntimeError("db down")
        mock_cls.return_value.close.return_value = None
        asyncio.run(audit_persist_cycle(bundle))


def test_reconcile_resting_orders_closes_stale_rows():
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(fetchone=MagicMock(return_value=None)),
        MagicMock(fetchall=MagicMock(return_value=[(1,), (2,), (3,)])),
    ]
    store = AuditStore(db=db)
    updated = store.reconcile_resting_orders(
        robot_id=1,
        executions=[
            AuditExecutionRow(
                ticker="ROSN",
                side="SELL",
                kind="exit_sl_tp",
                quantity=6,
                price=336.36,
                status="filled",
                mode="live",
                pnl=1.0,
                broker_order_id="oid-filled",
                order_type="LIMIT",
            ),
        ],
        open_broker_order_ids=set(),
        stop_reason="soft_stop_sync",
    )
    assert updated == 3
    assert db.commit.called


def test_reconcile_resting_orders_closes_stale_rows():
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(fetchone=MagicMock(return_value=None)),
        MagicMock(fetchall=MagicMock(return_value=[(1,), (2,), (3,)])),
    ]
    store = AuditStore(db=db)
    updated = store.reconcile_resting_orders(
        robot_id=1,
        executions=[
            AuditExecutionRow(
                ticker="ROSN",
                side="SELL",
                kind="exit_sl_tp",
                quantity=6,
                price=336.36,
                status="filled",
                mode="live",
                pnl=1.0,
                broker_order_id="oid-filled",
                order_type="LIMIT",
            ),
        ],
        open_broker_order_ids=set(),
        stop_reason="soft_stop_sync",
    )
    assert updated == 3
    assert db.commit.called
