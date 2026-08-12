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
from app.modules.robots_v2.engine.execution import ExecutionService
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
