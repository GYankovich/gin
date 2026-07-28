"""Broker sync: no sell without holdings; Stage4 skips flat broker symbols."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from datetime import datetime, timezone

from app.modules.robots.trading.stages.stage4_positions import Stage4Positions
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders


class _Broker:
    def __init__(self) -> None:
        self.posts: list[dict] = []
        self.open_orders: list[dict] = []

    async def get_orders(self, account_id: str):
        _ = account_id
        return list(self.open_orders)

    async def post_order(
        self,
        figi,
        quantity,
        price,
        direction,
        account_id,
        *,
        reduce_only: bool = False,
    ):
        self.posts.append(
            {
                "figi": figi,
                "quantity": quantity,
                "price": price,
                "direction": direction,
                "reduce_only": reduce_only,
            }
        )
        return {"orderId": f"oid-{len(self.posts)}", "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW"}

    async def get_last_price(self, user_id, figi):
        return None


def test_stage4_skips_exit_when_broker_flat():
    broker = _Broker()

    async def _run():
        stage = Stage4Positions(
            db=None,
            schema="ganaly",
            broker=broker,
            account_id="A",
            robot_id=24,
            log_func=lambda *_: None,
            cost_params={"broker_commission_rate": 0.0006, "ndfl_rate": 0.0},
        )
        positions = [
            {"id": 1, "figi": "TREEUSDT", "side": "buy", "quantity": 197.0, "entry_price": 0.04, "status": "open"}
        ]
        # TP would fire, but broker has 0 → no intent.
        out = await stage.plan_stop_loss_take_profit(
            positions,
            {"TREEUSDT": 0.05},
            {"stop_loss_percent": 2, "take_profit_percent": 3},
            account_positions={"TREEUSDT": 0.0},
        )
        assert out == []
        assert broker.posts == []

    asyncio.run(_run())


def test_stage4_clamps_qty_to_broker_long():
    broker = _Broker()

    async def _run():
        stage = Stage4Positions(
            db=None,
            schema="ganaly",
            broker=broker,
            account_id="A",
            robot_id=24,
            log_func=lambda *_: None,
            cost_params={"broker_commission_rate": 0.0006, "ndfl_rate": 0.0},
        )
        positions = [
            {"id": 1, "figi": "TREEUSDT", "side": "buy", "quantity": 197.0, "entry_price": 0.04, "status": "open"}
        ]
        out = await stage.plan_stop_loss_take_profit(
            positions,
            {"TREEUSDT": 0.05},
            {"stop_loss_percent": 2, "take_profit_percent": 3},
            account_positions={"TREEUSDT": 50.0},
        )
        assert len(out) == 1
        assert out[0].quantity == 50.0
        assert out[0].side == "SELL"

    asyncio.run(_run())


def test_stage6_skips_sell_without_long():
    broker = _Broker()

    async def _run():
        s6 = Stage6Orders(
            db=None,
            schema="ganaly",
            broker=broker,
            account_id="A",
            robot_id=1,
            token_id=1,
            user_id=1,
            log_func=lambda *_: None,
            account_positions={"TREEUSDT": 0.0},
            now_fn=lambda: datetime.now(timezone.utc),
        )
        out = await s6.execute_signals(
            [{
                "figi": "TREEUSDT",
                "signal": "SELL",
                "quantity": 197,
                "price": 0.035,
                "reduce_only": True,
                "intent_kind": "exit_sl_tp",
            }],
            risk_params={"enforce_session_hours": False, "min_trade_amount_rub": 0},
        )
        assert out[0]["status"] == "skipped"
        assert out[0]["error"] == "NO_ASSET_FOR_SELL"
        assert broker.posts == []

    asyncio.run(_run())


def test_stage6_skips_buy_reduce_when_no_short():
    broker = _Broker()

    async def _run():
        s6 = Stage6Orders(
            db=None,
            schema="ganaly",
            broker=broker,
            account_id="A",
            robot_id=1,
            token_id=1,
            user_id=1,
            log_func=lambda *_: None,
            account_positions={},  # flat
            now_fn=lambda: datetime.now(timezone.utc),
        )
        out = await s6.execute_signals(
            [{
                "figi": "SOSOUSDT",
                "signal": "BUY",
                "quantity": 114,
                "price": 0.28,
                "reduce_only": True,
                "intent_kind": "exit_sl_tp",
            }],
            risk_params={"enforce_session_hours": False, "min_trade_amount_rub": 0},
        )
        assert out[0]["status"] == "skipped"
        assert out[0]["error"] == "NO_POSITION_TO_CLOSE"
        assert broker.posts == []

    asyncio.run(_run())
