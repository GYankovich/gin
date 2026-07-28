from __future__ import annotations

import asyncio

from app.modules.robots.trading.backtest.metrics import BacktestMetricsCalculator
from app.modules.robots.trading.backtest.types import BacktestResult
from app.modules.robots.trading.brokers.sim_backtest import SimBacktestBrokerFacade
from app.modules.robots.trading.costs import (
    resolve_backtest_sim_rates,
    resolve_crypto_fee_rates,
    resolve_robot_cost_rates,
)
from app.modules.robots.trading.stages.stage6_orders import Stage6Orders


def test_resolve_robot_cost_rates_bybit_prefers_taker_and_no_ndfl():
    br, ndfl = resolve_robot_cost_rates(
        {
            "broker_type": "bybit",
            "costs": {"maker_fee_rate": 0.0001, "taker_fee_rate": 0.0007},
        }
    )
    assert br == 0.0007
    assert ndfl == 0.0


def test_resolve_backtest_sim_rates_bybit():
    br, maker, taker, ndfl = resolve_backtest_sim_rates(
        {
            "broker_type": "bybit",
            "costs": {"maker_fee_rate": 0.0001, "taker_fee_rate": 0.0006},
        }
    )
    assert br == 0.0006
    assert maker == 0.0001
    assert taker == 0.0006
    assert ndfl == 0.0


def test_resolve_crypto_fee_rates_defaults_and_override():
    m, t = resolve_crypto_fee_rates({})
    assert m == 0.0001 and t == 0.0006
    m2, t2 = resolve_crypto_fee_rates({"costs": {"maker_fee_rate": 0.0002}})
    assert m2 == 0.0002 and t2 == 0.0002


def test_stage6_cost_kw_uses_maker_fee_for_limit():
    s6 = Stage6Orders(
        db=None,
        schema="ganaly",
        broker=None,
        account_id="A",
        robot_id=1,
        token_id=1,
        user_id=1,
        cost_params={"broker_commission_rate": 0.0005, "ndfl_rate": 0.13, "maker_fee_rate": 0.0001, "taker_fee_rate": 0.0006},
    )
    kw = s6._cost_kw(is_market=False)
    assert kw["broker_commission_rate"] == 0.0001


def test_sim_backtest_broker_uses_maker_vs_taker():
    async def _run():
        b = SimBacktestBrokerFacade(
            initial_capital=1_000_000,
            candles_by_figi={},
            maker_fee_rate=0.0001,
            taker_fee_rate=0.0006,
            commission_rate=0.0001,
            ndfl_rate=0.0,
        )
        b.set_last_price("BTCUSDT", 100.0)
        limit_buy = await b.post_order("BTCUSDT", 10, 100.0, "ORDER_DIRECTION_BUY", "A")
        market_sell = await b.post_market_order("BTCUSDT", 10, "ORDER_DIRECTION_SELL", "A")
        comm_limit = float(limit_buy["executedCommission"]["units"])
        comm_market = float(market_sell["executedCommission"]["units"])
        assert comm_market >= comm_limit
        assert b.trade_log[0]["fee_kind"] == "maker"
        assert b.trade_log[1]["fee_kind"] == "taker"

    asyncio.run(_run())


def test_crypto_round_trip_pnl_excludes_ndfl():
    async def _run():
        b = SimBacktestBrokerFacade(
            initial_capital=1_000_000,
            candles_by_figi={},
            maker_fee_rate=0.0001,
            taker_fee_rate=0.0006,
            ndfl_rate=0.0,
        )
        b.set_last_price("BTCUSDT", 110.0)
        await b.post_order("BTCUSDT", 10, 100.0, "ORDER_DIRECTION_BUY", "A")
        await b.post_market_order("BTCUSDT", 10, "ORDER_DIRECTION_SELL", "A")
        sell = b.trade_log[-1]
        expected = b._calc_realized_pnl(
            entry_avg=100.0,
            exit_px=110.0,
            qty=10,
            entry_fee_rate=0.0001,
            exit_fee_rate=0.0006,
        )
        assert sell["pnl_net"] == expected
        # With 10% move and tiny fees, profit should be ~99 without 13% tax haircut.
        assert float(sell["pnl_net"] or 0) > 90.0

    asyncio.run(_run())


def test_fee_totals_and_metrics_match():
    async def _run():
        b = SimBacktestBrokerFacade(
            initial_capital=1_000_000,
            candles_by_figi={},
            maker_fee_rate=0.0001,
            taker_fee_rate=0.0006,
            ndfl_rate=0.0,
        )
        b.set_last_price("BTCUSDT", 100.0)
        await b.post_order("BTCUSDT", 10, 100.0, "ORDER_DIRECTION_BUY", "A")
        b.apply_funding_charge("BTCUSDT", 0.0001, bar_time="2024-06-01T08:00:00+00:00")
        totals = b.fee_totals()
        assert totals["maker_commission"] == 0.1
        assert totals["total_commission"] == 0.1
        assert totals["funding_paid"] == 0.1

        res = BacktestResult(
            initial_capital=1_000_000,
            final_equity=b._equity(),
            total_return_percent=0.0,
            max_drawdown_percent=None,
            trades=[{"commission": 0.1, "pnl_net": None}],
            fee_summary=totals,
        )
        m = BacktestMetricsCalculator.calculate(res=res)
        assert m["total_commission_val"] == 0.1
        assert m["total_funding_val"] == 0.1

    asyncio.run(_run())
