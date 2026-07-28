"""Fill-based account_positions: place does not mutate; FILL applies delta."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robots.trading.stages.stage6_orders import Stage6Orders


class _Broker:
    def __init__(self) -> None:
        self.posts: list[dict] = []

    async def get_last_price(self, user_id, figi):
        return 100.0

    async def post_order(self, figi, quantity, price, direction, account_id, *, reduce_only=False):
        self.posts.append(
            {"figi": figi, "quantity": quantity, "direction": direction, "reduce_only": reduce_only}
        )
        return {"orderId": "oid-1", "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW"}

    async def get_order_state(self, account_id, order_id):
        return {
            "orderId": order_id,
            "executionReportStatus": "EXECUTION_REPORT_STATUS_FILL",
            "lotsExecuted": 10.0,
            "lotsRequested": 10.0,
            "symbol": "BTCUSDT",
            "side": "Buy",
            "executedOrderPrice": {"units": 100, "nano": 0},
            "executedCommission": {"units": 0, "nano": 0},
            "stages": [],
        }


def test_stage6_place_does_not_mutate_book():
    book = {"BTCUSDT": 5.0}

    async def _run():
        s6 = Stage6Orders(
            db=None,
            schema="ganaly",
            broker=_Broker(),
            account_id="A",
            robot_id=1,
            token_id=1,
            user_id=1,
            log_func=lambda *_: None,
            account_positions=book,
            now_fn=lambda: datetime.now(timezone.utc),
        )
        out = await s6.execute_signals(
            [{"figi": "BTCUSDT", "signal": "BUY", "quantity": 10, "price": 100.0}],
            risk_params={
                "max_leverage": 1,
                "instrument_category": "spot",
                "margin_enabled": True,
                "enforce_session_hours": False,
                "free_funds": 10_000,
                "min_trade_amount_rub": 0,
            },
        )
        assert out[0]["order_id"] == "oid-1"
        assert book["BTCUSDT"] == 5.0  # unchanged until FILL
        assert "account_qty_after" not in out[0]

    asyncio.run(_run())


def test_apply_fill_incremental():
    from app.modules.robots.trading.session import TradingSession
    from app.modules.robots.trading.contracts import ExecutionMode

    # Minimal instance without full __init__ side effects — use a stub object.
    class _S:
        account_positions = {"BTCUSDT": 5.0}
        _order_fill_watches: dict = {}

        def _write_log(self, msg):
            pass

        register_order_fill_watch = TradingSession.register_order_fill_watch
        apply_fill_to_account_positions = TradingSession.apply_fill_to_account_positions
        clear_order_fill_watch = TradingSession.clear_order_fill_watch

    s = _S()
    TradingSession.register_order_fill_watch(s, order_id="oid-1", figi="BTCUSDT", side="BUY")
    TradingSession.apply_fill_to_account_positions(s, order_id="oid-1", filled_qty_total=4)
    assert s.account_positions["BTCUSDT"] == 9.0
    TradingSession.apply_fill_to_account_positions(s, order_id="oid-1", filled_qty_total=10)
    assert s.account_positions["BTCUSDT"] == 15.0
    # Idempotent re-poll
    TradingSession.apply_fill_to_account_positions(s, order_id="oid-1", filled_qty_total=10)
    assert s.account_positions["BTCUSDT"] == 15.0


def test_reject_does_not_require_revert():
    from app.modules.robots.trading.session import TradingSession

    class _S:
        account_positions = {"BTCUSDT": 5.0}
        _order_fill_watches: dict = {}

        def _write_log(self, msg):
            pass

        register_order_fill_watch = TradingSession.register_order_fill_watch
        clear_order_fill_watch = TradingSession.clear_order_fill_watch
        revert_optimistic_account_position = TradingSession.revert_optimistic_account_position

    s = _S()
    TradingSession.register_order_fill_watch(s, order_id="oid-1", figi="BTCUSDT", side="BUY")
    TradingSession.revert_optimistic_account_position(s, "oid-1")
    assert s.account_positions["BTCUSDT"] == 5.0
    assert "oid-1" not in s._order_fill_watches
