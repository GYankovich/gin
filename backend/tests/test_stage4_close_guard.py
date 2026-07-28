"""Stage4 SL/TP: decision-only intents + Execution place with reduceOnly."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.modules.robots.trading.contracts import OrderIntent
from app.modules.robots.trading.execution.service import LiveExecutionService, LiveExecutionContext
from app.modules.robots.trading.stages.stage4_positions import Stage4Positions
from app.modules.robots.trading.symbol_guard import SymbolGuard


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
                "account_id": account_id,
                "reduce_only": reduce_only,
            }
        )
        return {"orderId": f"oid-{len(self.posts)}", "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW"}

    async def get_last_price(self, user_id, figi):
        return None


def _stage4(broker: _Broker) -> Stage4Positions:
    return Stage4Positions(
        db=None,
        schema="ganaly",
        broker=broker,
        account_id="A",
        robot_id=24,
        log_func=lambda *_: None,
        cost_params={"broker_commission_rate": 0.0006, "ndfl_rate": 0.0},
    )


def test_stage4_skips_when_figi_already_pending_close():
    broker = _Broker()

    async def _run():
        stage = _stage4(broker)
        positions = [
            {"id": 1, "figi": "TREEUSDT", "side": "buy", "quantity": 197.0, "entry_price": 0.04, "status": "open"}
        ]
        out = await stage.plan_stop_loss_take_profit(
            positions,
            {"TREEUSDT": 0.05},
            {"stop_loss_percent": 2, "take_profit_percent": 3},
            pending_close_figis={"TREEUSDT"},
        )
        assert out == []
        assert broker.posts == []

    asyncio.run(_run())


def test_stage4_skips_when_broker_already_has_active_order():
    broker = _Broker()
    broker.open_orders = [
        {
            "orderId": "existing",
            "symbol": "TREEUSDT",
            "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW",
        }
    ]

    async def _run():
        stage = _stage4(broker)
        positions = [
            {"id": 1, "figi": "TREEUSDT", "side": "buy", "quantity": 197.0, "entry_price": 0.04, "status": "open"}
        ]
        out = await stage.plan_stop_loss_take_profit(
            positions,
            {"TREEUSDT": 0.05},
            {"stop_loss_percent": 2, "take_profit_percent": 3},
            pending_close_figis=set(),
        )
        assert out == []
        assert broker.posts == []

    asyncio.run(_run())


def test_stage4_plans_intent_without_post_order():
    broker = _Broker()

    async def _run():
        stage = _stage4(broker)
        positions = [
            {"id": 1, "figi": "TREEUSDT", "side": "buy", "quantity": 197.0, "entry_price": 0.04, "status": "open"}
        ]
        out = await stage.plan_stop_loss_take_profit(
            positions,
            {"TREEUSDT": 0.05},
            {"stop_loss_percent": 2, "take_profit_percent": 3},
            pending_close_figis=set(),
        )
        assert len(out) == 1
        assert isinstance(out[0], OrderIntent)
        assert out[0].kind == "exit_sl_tp"
        assert out[0].reduce_only is True
        assert out[0].side == "SELL"
        assert broker.posts == []

        # Second cycle with pending figi must not plan again.
        out2 = await stage.plan_stop_loss_take_profit(
            positions,
            {"TREEUSDT": 0.05},
            {"stop_loss_percent": 2, "take_profit_percent": 3},
            pending_close_figis={"TREEUSDT"},
        )
        assert out2 == []
        assert broker.posts == []

    asyncio.run(_run())


def test_execution_places_single_reduce_only_close_from_intent():
    broker = _Broker()

    async def _run():
        stage = _stage4(broker)
        positions = [
            {"id": 1, "figi": "TREEUSDT", "side": "buy", "quantity": 197.0, "entry_price": 0.04, "status": "open"}
        ]
        intents = await stage.plan_stop_loss_take_profit(
            positions,
            {"TREEUSDT": 0.05},
            {"stop_loss_percent": 2, "take_profit_percent": 3},
        )
        in_flight: dict[str, str] = {}
        pending: dict[str, dict] = {}
        guard = SymbolGuard(in_flight_orders=in_flight, pending_position_closures=pending)
        ctx = LiveExecutionContext(
            db=None,
            schema="ganaly",
            broker=broker,
            account_id="A",
            robot_id=24,
            token_id=1,
            user_id=1,
            log_func=lambda *_: None,
            in_flight_orders=in_flight,
            account_positions={"TREEUSDT": 197.0},
            cost_params={"broker_commission_rate": 0.0006, "ndfl_rate": 0.0},
            now_fn=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )
        execution = LiveExecutionService(ctx)
        trades = await execution.submit_intents(
            intents,
            risk_params={"enforce_session_hours": False, "min_trade_amount_rub": 0},
        )
        assert len(trades) == 1
        assert trades[0]["order_id"] == "oid-1"
        assert trades[0]["intent_source"] == "exit_sl_tp"
        assert len(broker.posts) == 1
        assert broker.posts[0]["reduce_only"] is True
        assert "SELL" in str(broker.posts[0]["direction"]).upper()

        guard.register_pending_close(trades[0]["order_id"], {
            "figi": "TREEUSDT",
            "trade_id": 1,
            "order_id": trades[0]["order_id"],
        })

        # Second cycle: Stage4 blocked by guard, no second place.
        intents2 = await stage.plan_stop_loss_take_profit(
            positions,
            {"TREEUSDT": 0.05},
            {"stop_loss_percent": 2, "take_profit_percent": 3},
            pending_close_figis=guard.blocked_figis(),
            guard=guard,
        )
        assert intents2 == []
        trades2 = await execution.submit_intents(intents2)
        assert trades2 == []
        assert len(broker.posts) == 1

    asyncio.run(_run())
