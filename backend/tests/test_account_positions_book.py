"""account_positions live book: apply / revert / shared Stage6 mutations."""

from __future__ import annotations

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robots.trading.account_positions_book import (
    apply_trade_to_account_positions,
    revert_trade_on_account_positions,
    signed_qty,
)
from app.modules.robots.trading.execution.service import LiveExecutionContext, LiveExecutionService
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders


def test_apply_buy_sell_and_flat():
    book: dict[str, float] = {}
    assert apply_trade_to_account_positions(book, figi="AAAUSDT", side="BUY", quantity=10) == 10.0
    assert book["AAAUSDT"] == 10.0
    assert apply_trade_to_account_positions(book, figi="AAAUSDT", side="SELL", quantity=4) == 6.0
    assert apply_trade_to_account_positions(book, figi="AAAUSDT", side="SELL", quantity=6) == 0.0
    assert "AAAUSDT" not in book


def test_revert_undoes_optimistic_buy():
    book = {"BBBUSDT": 5.0}
    apply_trade_to_account_positions(book, figi="BBBUSDT", side="BUY", quantity=3)
    assert signed_qty(book, "BBBUSDT") == 8.0
    revert_trade_on_account_positions(book, figi="BBBUSDT", side="BUY", quantity=3)
    assert signed_qty(book, "BBBUSDT") == 5.0


def test_stage6_mutates_shared_session_book():
    session_book = {"TREEUSDT": 100.0}
    stage = Stage6Orders(
        db=None,
        schema="ganaly",
        broker=None,
        account_id="A",
        robot_id=1,
        token_id=1,
        user_id=1,
        log_func=None,
        account_positions=session_book,
    )
    apply_trade_to_account_positions(
        stage.account_positions, figi="TREEUSDT", side="SELL", quantity=40
    )
    assert session_book["TREEUSDT"] == 60.0
    assert stage.account_positions is session_book


def test_sync_counters_does_not_wipe_shared_book():
    session_book = {"XUSDT": 10.0}
    ctx = LiveExecutionContext(
        db=None,
        schema="ganaly",
        broker=None,
        account_id="A",
        robot_id=1,
        token_id=1,
        user_id=1,
        account_positions=session_book,
        daily_trade_counter={},
        last_trade_by_figi={},
        in_flight_orders={},
    )
    svc = LiveExecutionService(ctx)
    stage = svc._stage()
    apply_trade_to_account_positions(stage.account_positions, figi="XUSDT", side="BUY", quantity=5)
    assert session_book["XUSDT"] == 15.0
    svc.sync_counters_from_stage()
    assert session_book["XUSDT"] == 15.0
    assert stage.account_positions is session_book
