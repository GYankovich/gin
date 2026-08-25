"""Tests for execution service + order-flow aggregator."""

import os
from datetime import datetime, timezone

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

import asyncio

from app.modules.robots.trading.contracts import OrderIntent
from app.modules.robots_v2.engine.execution import ExecutionService, attach_ticker_warnings
from app.modules.robots_v2.engine.order_flow import OrderFlowAggregator
from app.modules.robots_v2.engine.paper_ledger import PaperLedger


def test_order_flow_delta_from_price_ticks():
    agg = OrderFlowAggregator(window_sec=60)
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    agg.on_price("BTCUSDT", 100.0, volume=1.0, now=now)
    agg.on_price("BTCUSDT", 101.0, volume=1.0, now=now)  # uptick → buy
    agg.on_price("BTCUSDT", 99.0, volume=1.0, now=now)   # downtick → sell
    snap = agg.snapshot("BTCUSDT", now=now)
    assert snap is not None
    # notional ≈ price * size
    assert snap.buy_volume == 100.0 + 101.0
    assert snap.sell_volume == 99.0
    assert snap.delta_pct > 0
    assert snap.tick_count == 3
    assert snap.trade_count == 0
    assert snap.has_real_trades is False
    assert snap.flow_source == "inferred"


def test_order_flow_prefers_real_trades():
    agg = OrderFlowAggregator(window_sec=60)
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    agg.on_trade("ETHUSDT", price=2000.0, side="Buy", volume=0.5, turnover=1000.0, now=now)
    agg.on_trade("ETHUSDT", price=1990.0, side="Sell", volume=0.1, turnover=199.0, now=now)
    # price ticks ignored once real trades present
    agg.on_price("ETHUSDT", 2100.0, volume=1.0, now=now)
    snap = agg.snapshot("ETHUSDT", now=now)
    assert snap is not None
    assert snap.buy_volume == 1000.0
    assert snap.sell_volume == 199.0
    assert snap.tick_count == 2
    assert snap.trade_count == 2
    assert snap.has_real_trades is True
    assert snap.flow_source == "trades"


def test_execution_paper_fill():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    exec_svc = ExecutionService(mode="paper", robot_id=1, ledger=ledger, slippage_pct=0)
    intent = OrderIntent(kind="entry", figi="SBER", side="BUY", quantity=10, price=100.0)

    async def _run():
        return await exec_svc.execute_intent(intent, last_price=100.0)

    result = asyncio.run(_run())
    assert result.status == "filled"
    assert "SBER" in ledger.positions


def test_execution_live_rejects_without_broker():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    exec_svc = ExecutionService(mode="live", robot_id=1, ledger=ledger)
    intent = OrderIntent(kind="entry", figi="SBER", side="BUY", quantity=1, price=100.0)

    async def _run():
        return await exec_svc.execute_intent(intent, last_price=100.0)

    result = asyncio.run(_run())
    assert result.status == "rejected"
    assert result.reason == "BROKER_OR_ACCOUNT_MISSING"


def test_resolve_bybit_instrument_map_identity():
    from app.modules.robots_v2.engine.broker_factory import resolve_ticker_instrument_map
    from app.modules.robots_v2.universe.token_context import TokenContext

    ctx = TokenContext(
        token_id=1, user_id=1, token_type=2, broker="bybit", market="crypto",
        api_key="k", api_secret="s", testnet=True,
    )

    async def _run():
        return await resolve_ticker_instrument_map(ctx, ["btcusdt", "ETHUSDT"])

    m = asyncio.run(_run())
    assert m == {"BTCUSDT": "BTCUSDT", "ETHUSDT": "ETHUSDT"}


def test_symbol_guard_blocks_second_inflight():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    exec_svc = ExecutionService(
        mode="live", robot_id=1, ledger=ledger, account_id="acc",
        fill_poll_interval_sec=0.05, fill_timeout_sec=2.0,
    )

    class _Broker:
        broker_type = "bybit"

        async def post_market_order(self, *args, **kwargs):
            await asyncio.sleep(0.08)
            return {"orderId": "1"}

        async def get_order_state(self, account_id, order_id):
            await asyncio.sleep(0.05)
            return {
                "executionReportStatus": "EXECUTION_REPORT_STATUS_FILL",
                "lotsExecuted": 1,
                "executedOrderPrice": 100.0,
            }

    exec_svc.broker = _Broker()  # type: ignore[assignment]
    intent = OrderIntent(kind="entry", figi="BTCUSDT", side="BUY", quantity=1, price=100.0)

    async def _run():
        t1 = asyncio.create_task(exec_svc.execute_intent(intent, last_price=100.0))
        await asyncio.sleep(0.02)
        r2 = await exec_svc.execute_intent(intent, last_price=100.0)
        r1 = await t1
        return r1, r2

    r1, r2 = asyncio.run(_run())
    assert r1.status == "filled"
    assert r2.status == "rejected"
    assert r2.reason == "IN_FLIGHT_ORDER"
    assert "BTCUSDT" in ledger.positions


def test_live_fill_confirmation_applies_ledger():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    exec_svc = ExecutionService(
        mode="live", robot_id=1, ledger=ledger, account_id="acc",
        fill_poll_interval_sec=0.01, fill_timeout_sec=2.0,
    )

    class _Broker:
        broker_type = "bybit"
        calls = 0

        async def post_market_order(self, *args, **kwargs):
            return {"orderId": "oid-9"}

        async def get_order_state(self, account_id, order_id):
            self.calls += 1
            if self.calls < 2:
                return {"executionReportStatus": "EXECUTION_REPORT_STATUS_NEW", "lotsExecuted": 0}
            return {
                "executionReportStatus": "EXECUTION_REPORT_STATUS_FILL",
                "lotsExecuted": 3,
                "executedOrderPrice": 101.5,
            }

    exec_svc.broker = _Broker()  # type: ignore[assignment]
    intent = OrderIntent(kind="entry", figi="ETHUSDT", side="BUY", quantity=3, price=100.0)

    async def _run():
        return await exec_svc.execute_intent(intent, last_price=100.0)

    result = asyncio.run(_run())
    assert result.status == "filled"
    assert result.price == 101.5
    assert result.quantity == 3
    assert ledger.positions["ETHUSDT"].quantity == 3


def test_live_fill_timeout_does_not_mutate_ledger():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    exec_svc = ExecutionService(
        mode="live", robot_id=1, ledger=ledger, account_id="acc",
        fill_poll_interval_sec=0.01, fill_timeout_sec=0.05,
    )

    class _Broker:
        broker_type = "bybit"

        async def post_market_order(self, *args, **kwargs):
            return {"orderId": "oid-slow"}

        async def get_order_state(self, account_id, order_id):
            return {"executionReportStatus": "EXECUTION_REPORT_STATUS_NEW", "lotsExecuted": 0}

    exec_svc.broker = _Broker()  # type: ignore[assignment]
    intent = OrderIntent(kind="entry", figi="SOLUSDT", side="BUY", quantity=1, price=50.0)

    async def _run():
        return await exec_svc.execute_intent(intent, last_price=50.0)

    result = asyncio.run(_run())
    assert result.status == "submitted"
    assert result.reason == "FILL_CONFIRM_TIMEOUT"
    assert "SOLUSDT" not in ledger.positions


def test_reconcile_overwrites_shadow_ledger():
    from app.modules.robots_v2.engine.reconcile import reconcile_from_broker

    ledger = PaperLedger(cash=10_000, commission_rate=0.0)
    ledger.apply_fill(ticker="SBER", side="BUY", quantity=5, price=200.0)

    class _Broker:
        async def get_portfolio(self, account_id):
            return {
                "positions": [
                    {
                        "figi": "BBG004730N88",
                        "ticker": "SBER",
                        "quantity": {"decimal": 10},
                        "average_position_price": {"decimal": 250.0},
                        "current_price": {"decimal": 260.0},
                    }
                ]
            }

        async def get_free_funds(self, account_id):
            return 55_000.0

    async def _run():
        return await reconcile_from_broker(
            robot_id=1,
            broker=_Broker(),  # type: ignore[arg-type]
            account_id="acc",
            ledger=ledger,
            instrument_map={"SBER": "BBG004730N88"},
            universe=["SBER"],
        )

    rec = asyncio.run(_run())
    assert rec.ok
    assert ledger.cash == 55_000.0
    assert ledger.positions["SBER"].quantity == 10
    assert ledger.positions["SBER"].avg_entry_price == 250.0
    assert any(d.get("field") == "cash" for d in rec.diffs)


def test_reconcile_preserves_opened_at():
    from datetime import datetime, timedelta, timezone

    from app.modules.robots_v2.engine.reconcile import reconcile_from_broker

    opened = datetime.now(timezone.utc) - timedelta(minutes=10)
    ledger = PaperLedger(cash=10_000, commission_rate=0.0)
    ledger.apply_fill(ticker="SFIN", side="BUY", quantity=3, price=590.0)
    ledger.positions["SFIN"].opened_at = opened

    class _Broker:
        async def get_portfolio(self, account_id):
            return {
                "positions": [
                    {
                        "figi": "BBG004S681P4",
                        "ticker": "SFIN",
                        "quantity": {"decimal": 3},
                        "average_position_price": {"decimal": 590.0},
                        "current_price": {"decimal": 595.0},
                    }
                ]
            }

        async def get_free_funds(self, account_id):
            return 10_000.0

    async def _run():
        return await reconcile_from_broker(
            robot_id=1,
            broker=_Broker(),  # type: ignore[arg-type]
            account_id="acc",
            ledger=ledger,
            instrument_map={"SFIN": "BBG004S681P4"},
            universe=["SFIN"],
        )

    rec = asyncio.run(_run())
    assert rec.ok
    assert ledger.positions["SFIN"].opened_at == opened


def test_paper_limit_rests_when_mark_below_tp_sell():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    ledger.apply_fill(ticker="TREEUSDT", side="BUY", quantity=10, price=1.0)
    exec_svc = ExecutionService(mode="paper", robot_id=1, ledger=ledger, slippage_pct=0)
    intent = OrderIntent(
        kind="exit_sl_tp",
        figi="TREEUSDT",
        side="SELL",
        quantity=10,
        price=1.03,
        order_type="LIMIT",
        reduce_only=True,
        reason="take_profit",
    )

    async def _run():
        return await exec_svc.execute_intent(intent, last_price=1.02)

    result = asyncio.run(_run())
    assert result.status == "resting"
    assert "TREEUSDT" in exec_svc._resting
    assert "TREEUSDT" in ledger.positions


def test_paper_limit_fills_when_mark_crosses():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    ledger.apply_fill(ticker="TREEUSDT", side="BUY", quantity=10, price=1.0)
    exec_svc = ExecutionService(mode="paper", robot_id=1, ledger=ledger, slippage_pct=0)
    intent = OrderIntent(
        kind="exit_sl_tp",
        figi="TREEUSDT",
        side="SELL",
        quantity=10,
        price=1.03,
        order_type="LIMIT",
        reduce_only=True,
        reason="take_profit",
    )

    async def _run():
        r1 = await exec_svc.execute_intent(intent, last_price=1.02)
        fills = await exec_svc.poll_resting_fills(last_prices={"TREEUSDT": 1.04})
        return r1, fills

    r1, fills = asyncio.run(_run())
    assert r1.status == "resting"
    assert len(fills) == 1
    assert fills[0].status == "filled"
    assert fills[0].price == 1.03
    assert "TREEUSDT" not in ledger.positions


def test_paper_limit_identical_returns_already_resting():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    exec_svc = ExecutionService(mode="paper", robot_id=1, ledger=ledger, slippage_pct=0)
    intent = OrderIntent(
        kind="exit_sl_tp",
        figi="TREEUSDT",
        side="SELL",
        quantity=10,
        price=1.03,
        order_type="LIMIT",
        reduce_only=True,
        reason="take_profit",
    )

    async def _run():
        r1 = await exec_svc.execute_intent(intent, last_price=1.02)
        r2 = await exec_svc.execute_intent(intent, last_price=1.02)
        return r1, r2

    r1, r2 = asyncio.run(_run())
    assert r1.status == "resting"
    assert r2.status == "resting"
    assert r2.reason == "ALREADY_RESTING"


def test_market_stop_loss_clears_resting():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    ledger.apply_fill(ticker="TREEUSDT", side="BUY", quantity=10, price=1.0)
    exec_svc = ExecutionService(mode="paper", robot_id=1, ledger=ledger, slippage_pct=0)
    limit_intent = OrderIntent(
        kind="exit_sl_tp",
        figi="TREEUSDT",
        side="SELL",
        quantity=10,
        price=1.03,
        order_type="LIMIT",
        reduce_only=True,
        reason="take_profit",
    )
    sl_intent = OrderIntent(
        kind="exit_sl_tp",
        figi="TREEUSDT",
        side="SELL",
        quantity=10,
        price=0.97,
        order_type="MARKET",
        reduce_only=True,
        reason="stop_loss",
    )

    async def _run():
        r1 = await exec_svc.execute_intent(limit_intent, last_price=1.02)
        assert "TREEUSDT" in exec_svc._resting
        r2 = await exec_svc.execute_intent(sl_intent, last_price=0.97)
        return r1, r2

    r1, r2 = asyncio.run(_run())
    assert r1.status == "resting"
    assert r2.status == "filled"
    assert "TREEUSDT" not in exec_svc._resting
    assert "TREEUSDT" not in ledger.positions


def test_normalize_and_scope_filter_orders():
    from app.modules.robots_v2.engine.order_sync import (
        filter_robot_scope_orders,
        normalize_broker_orders,
        pick_resting_per_ticker,
    )

    rows = [
        {
            "orderId": "oid-sfin",
            "figi": "BBG004S681P4",
            "direction": "ORDER_DIRECTION_SELL",
            "lotsRequested": 3,
            "initialOrderPrice": {"units": 600, "nano": 0},
            "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW",
            "orderType": "ORDER_TYPE_LIMIT",
        },
        {
            "orderId": "oid-foreign",
            "figi": "BBG004730N88",
            "direction": "ORDER_DIRECTION_BUY",
            "lotsRequested": 1,
            "price": 250.0,
            "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW",
            "orderType": "ORDER_TYPE_LIMIT",
        },
    ]
    norm = normalize_broker_orders(
        rows,
        instrument_map={"SFIN": "BBG004S681P4", "SBER": "BBG004730N88"},
    )
    assert len(norm) == 2
    scoped = filter_robot_scope_orders(
        norm,
        position_tickers={"SFIN"},
        known_order_ids=set(),
    )
    assert [o.order_id for o in scoped] == ["oid-sfin"]
    picked = pick_resting_per_ticker(scoped)
    assert "SFIN" in picked
    assert picked["SFIN"].limit_price == 600.0


def test_sync_orders_adopts_broker_resting():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    ledger.apply_fill(ticker="SFIN", side="BUY", quantity=3, price=590.0)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=1,
        ledger=ledger,
        account_id="acc",
        instrument_map={"SFIN": "BBG004S681P4"},
    )

    class _Broker:
        broker_type = "tinvest"

        async def get_orders(self, account_id):
            return [
                {
                    "orderId": "oid-1",
                    "figi": "BBG004S681P4",
                    "direction": "ORDER_DIRECTION_SELL",
                    "lotsRequested": 3,
                    "initialOrderPrice": {"units": 610, "nano": 0},
                    "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW",
                    "orderType": "ORDER_TYPE_LIMIT",
                }
            ]

    exec_svc.broker = _Broker()  # type: ignore[assignment]

    async def _run():
        return await exec_svc.sync_orders_from_broker(force=True)

    results = asyncio.run(_run())
    assert results == []
    assert "SFIN" in exec_svc._resting
    ro = exec_svc._resting["SFIN"]
    assert ro.broker_order_id == "oid-1"
    assert ro.limit_price == 610.0
    assert ro.side == "SELL"


def test_sync_orders_fill_when_missing_from_get_orders():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    ledger.apply_fill(ticker="X5", side="BUY", quantity=1, price=2000.0)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=1,
        ledger=ledger,
        account_id="acc",
        instrument_map={"X5": "BBG00Y91R9K8"},
    )
    from app.modules.robots_v2.engine.execution import RestingOrder

    exec_svc._resting["X5"] = RestingOrder(
        intent_id="i1",
        ticker="X5",
        side="SELL",
        quantity=1,
        limit_price=2050.5,
        reduce_only=True,
        reason="take_profit",
        kind="exit_sl_tp",
        broker_order_id="oid-x5",
    )

    class _Broker:
        broker_type = "tinvest"

        async def get_orders(self, account_id):
            return []

        async def get_order_state(self, account_id, order_id):
            return {
                "executionReportStatus": "EXECUTION_REPORT_STATUS_FILL",
                "lotsExecuted": 1,
                "executedOrderPrice": {"units": 2050, "nano": 500_000_000},
            }

    exec_svc.broker = _Broker()  # type: ignore[assignment]

    async def _run():
        return await exec_svc.sync_orders_from_broker(force=True)

    results = asyncio.run(_run())
    assert len(results) == 1
    assert results[0].status == "filled"
    assert "X5" not in exec_svc._resting
    assert "X5" not in ledger.positions


def test_sync_orders_cancelled_when_missing():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    ledger.apply_fill(ticker="MGNT", side="BUY", quantity=1, price=5000.0)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=1,
        ledger=ledger,
        account_id="acc",
        instrument_map={"MGNT": "BBG004RVFCY3"},
    )
    from app.modules.robots_v2.engine.execution import RestingOrder

    exec_svc._resting["MGNT"] = RestingOrder(
        intent_id="i2",
        ticker="MGNT",
        side="SELL",
        quantity=1,
        limit_price=5100.0,
        broker_order_id="oid-mgnt",
        kind="exit_sl_tp",
    )

    class _Broker:
        broker_type = "tinvest"

        async def get_orders(self, account_id):
            return []

        async def get_order_state(self, account_id, order_id):
            return {
                "executionReportStatus": "EXECUTION_REPORT_STATUS_CANCELLED",
                "message": "Application period has ended",
            }

    exec_svc.broker = _Broker()  # type: ignore[assignment]

    async def _run():
        return await exec_svc.sync_orders_from_broker(force=True)

    results = asyncio.run(_run())
    assert len(results) == 1
    assert results[0].status == "cancelled"
    assert "Application period" in (results[0].reason or "")
    assert "MGNT" not in exec_svc._resting
    assert "MGNT" in ledger.positions


def test_sync_orders_ignores_foreign_ticker_without_position():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    ledger.apply_fill(ticker="SFIN", side="BUY", quantity=1, price=600.0)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=1,
        ledger=ledger,
        account_id="acc",
        instrument_map={"SFIN": "BBG004S681P4", "SBER": "BBG004730N88"},
    )

    class _Broker:
        broker_type = "tinvest"

        async def get_orders(self, account_id):
            return [
                {
                    "orderId": "oid-sber",
                    "figi": "BBG004730N88",
                    "direction": "ORDER_DIRECTION_SELL",
                    "lotsRequested": 10,
                    "price": 300.0,
                    "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW",
                    "orderType": "ORDER_TYPE_LIMIT",
                },
                {
                    "orderId": "oid-sfin",
                    "figi": "BBG004S681P4",
                    "direction": "ORDER_DIRECTION_SELL",
                    "lotsRequested": 1,
                    "price": 620.0,
                    "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW",
                    "orderType": "ORDER_TYPE_LIMIT",
                },
            ]

    exec_svc.broker = _Broker()  # type: ignore[assignment]
    asyncio.run(exec_svc.sync_orders_from_broker(force=True))
    assert set(exec_svc._resting.keys()) == {"SFIN"}
    assert exec_svc._resting["SFIN"].broker_order_id == "oid-sfin"


def test_limit_already_resting_after_broker_sync():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    ledger.apply_fill(ticker="SFIN", side="BUY", quantity=3, price=590.0)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=1,
        ledger=ledger,
        account_id="acc",
        instrument_map={"SFIN": "BBG004S681P4"},
    )
    from app.modules.robots_v2.engine.execution import RestingOrder

    exec_svc._resting["SFIN"] = RestingOrder(
        intent_id="i",
        ticker="SFIN",
        side="SELL",
        quantity=3,
        limit_price=610.0,
        broker_order_id="oid-1",
        kind="exit_sl_tp",
        reason="take_profit",
    )
    intent = OrderIntent(
        kind="exit_sl_tp",
        figi="SFIN",
        side="SELL",
        quantity=3,
        price=610.0,
        order_type="LIMIT",
        reduce_only=True,
        reason="take_profit",
    )

    async def _run():
        return await exec_svc.execute_intent(intent, last_price=600.0)

    result = asyncio.run(_run())
    assert result.status == "resting"
    assert result.reason == "ALREADY_RESTING"


def test_adopt_broker_limit_blocks_duplicate_post():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    ledger.apply_fill(ticker="ROSN", side="BUY", quantity=6, price=332.2)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=1,
        ledger=ledger,
        account_id="acc",
        instrument_map={"ROSN": "BBG004731354"},
    )
    posted: list[str] = []

    class _Broker:
        broker_type = "tinvest"

        async def get_orders(self, account_id):
            return [
                {
                    "orderId": "oid-existing",
                    "figi": "BBG004731354",
                    "direction": "ORDER_DIRECTION_SELL",
                    "lotsRequested": 6,
                    "initialOrderPrice": {"units": 336, "nano": 360000000},
                    "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW",
                    "orderType": "ORDER_TYPE_LIMIT",
                }
            ]

        async def post_order(self, *args, **kwargs):
            posted.append("called")
            return {"orderId": "oid-new"}

    exec_svc.broker = _Broker()  # type: ignore[assignment]
    intent = OrderIntent(
        kind="exit_sl_tp",
        figi="ROSN",
        side="SELL",
        quantity=6,
        price=336.36,
        order_type="LIMIT",
        reduce_only=True,
        reason="take_profit",
    )

    async def _run():
        return await exec_svc.execute_intent(intent, last_price=336.0)

    result = asyncio.run(_run())
    assert result.status == "resting"
    assert result.reason == "ALREADY_RESTING"
    assert posted == []
    assert exec_svc._resting["ROSN"].broker_order_id == "oid-existing"


def test_sync_cancels_duplicate_tp_on_same_ticker():
    ledger = PaperLedger(cash=100_000, commission_rate=0.0)
    ledger.apply_fill(ticker="ROSN", side="BUY", quantity=6, price=332.2)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=1,
        ledger=ledger,
        account_id="acc",
        instrument_map={"ROSN": "BBG004731354"},
    )
    cancelled: list[str] = []

    class _Broker:
        broker_type = "tinvest"

        async def get_orders(self, account_id):
            return [
                {
                    "orderId": "oid-a",
                    "figi": "BBG004731354",
                    "direction": "ORDER_DIRECTION_SELL",
                    "lotsRequested": 6,
                    "initialOrderPrice": {"units": 336, "nano": 360000000},
                    "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW",
                    "orderType": "ORDER_TYPE_LIMIT",
                },
                {
                    "orderId": "oid-b",
                    "figi": "BBG004731354",
                    "direction": "ORDER_DIRECTION_SELL",
                    "lotsRequested": 6,
                    "initialOrderPrice": {"units": 336, "nano": 360000000},
                    "executionReportStatus": "EXECUTION_REPORT_STATUS_NEW",
                    "orderType": "ORDER_TYPE_LIMIT",
                },
            ]

        async def cancel_order(self, account_id, order_id):
            cancelled.append(str(order_id))

    exec_svc.broker = _Broker()  # type: ignore[assignment]
    results = asyncio.run(exec_svc.sync_orders_from_broker(force=True))
    assert len(cancelled) == 1
    assert cancelled[0] in {"oid-a", "oid-b"}
    assert len(exec_svc._resting) == 1
    assert any(r.status == "cancelled" and r.reason == "DUPLICATE_TP" for r in results)


def test_update_instrument_map_prefers_figi_over_ticker():
    ledger = PaperLedger(cash=10_000, commission_rate=0.0)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=3,
        ledger=ledger,
        instrument_map={"NVTK": "BBG00475KKY8"},
    )
    exec_svc.update_instrument_map({"GMKN": "GMKN", "OZON": "BBG00Y91R9T3"})
    assert exec_svc._instrument_id("NVTK") == "BBG00475KKY8"
    assert exec_svc._instrument_id("GMKN") == "GMKN"
    exec_svc.update_instrument_map({"GMKN": "BBG004S68614"})
    assert exec_svc._instrument_id("GMKN") == "BBG004S68614"
    assert exec_svc._instrument_id("OZON") == "BBG00Y91R9T3"


def test_live_tinvest_skips_order_without_figi():
    ledger = PaperLedger(cash=10_000, commission_rate=0.0)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=3,
        ledger=ledger,
        account_id="2027062159",
        instrument_map={"NVTK": "BBG00475KKY8"},
    )
    posted: list[str] = []

    class _Broker:
        broker_type = "tinvest"

        async def post_market_order(self, instrument, qty, direction, account_id):
            posted.append(instrument)
            return {"orderId": "should-not-run"}

    exec_svc.broker = _Broker()  # type: ignore[assignment]
    intent = OrderIntent(kind="entry", figi="PLZL", side="BUY", quantity=1, price=1160.0)
    result = asyncio.run(exec_svc.execute_intent(intent, last_price=1160.0))
    assert result.status == "rejected"
    assert result.reason == "FIGI_UNRESOLVED"
    assert posted == []

    exec_svc.update_instrument_map({"PLZL": "BBG000R607Y3"})
    assert exec_svc._instrument_id("PLZL") == "BBG000R607Y3"


def test_ticker_warning_on_figi_unresolved_and_clears():
    ledger = PaperLedger(cash=10_000, commission_rate=0.0)
    exec_svc = ExecutionService(
        mode="live",
        robot_id=3,
        ledger=ledger,
        account_id="2027062159",
        instrument_map={"PLZL": "PLZL"},
    )

    class _Broker:
        broker_type = "tinvest"

        async def post_market_order(self, instrument, qty, direction, account_id):
            raise AssertionError("must not submit without FIGI")

    exec_svc.broker = _Broker()  # type: ignore[assignment]
    intent = OrderIntent(kind="entry", figi="PLZL", side="BUY", quantity=1, price=1160.0)
    result = asyncio.run(exec_svc.execute_intent(intent, last_price=1160.0))
    assert result.status == "rejected"
    assert result.reason == "FIGI_UNRESOLVED"
    warn = exec_svc.ticker_warning("PLZL")
    assert warn is not None
    assert "FIGI" in warn
    rows = attach_ticker_warnings(
        [{"ticker": "PLZL", "quantity": 1}],
        exec_svc,
        last_prices={"PLZL": 1160.0},
    )
    assert rows[0]["tickerWarning"] == warn
    exec_svc.update_instrument_map({"PLZL": "BBG000R607Y3"})
    assert exec_svc.ticker_warning("PLZL", last_price=1160.0) is None
    cleared = attach_ticker_warnings(
        [{"ticker": "PLZL", "quantity": 1}],
        exec_svc,
        last_prices={"PLZL": 1160.0},
    )
    assert "tickerWarning" not in cleared[0]


def test_ticker_warning_missing_quote_and_broker_404():
    ledger = PaperLedger(cash=10_000, commission_rate=0.0)
    exec_svc = ExecutionService(mode="live", robot_id=3, ledger=ledger)
    exec_svc.note_ticker_issue("NVTK", "404 Instrument not found (50002)")
    rows = attach_ticker_warnings(
        [{"ticker": "NVTK", "quantity": 2}, {"ticker": "ROSN", "quantity": 1}],
        exec_svc,
        last_prices={"ROSN": 0},
    )
    assert "не нашёл инструмент" in rows[0]["tickerWarning"]
    assert "котировки" in rows[1]["tickerWarning"]
