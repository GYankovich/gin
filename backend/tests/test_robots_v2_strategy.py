"""Unit tests for Strategy Runtime v2 plugins."""

import os
from datetime import datetime, timezone
from uuid import uuid4

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.modules.robots.trading.contracts import Candle, Position
from app.modules.robots_v2.config.v4_schema import StrategyConfig
from app.modules.robots_v2.strategy.registry import create_plugin, list_archetypes
from app.modules.robots_v2.strategy.runtime import StrategyRuntime
from app.modules.robots_v2.strategy.schemas import OrderFlowSnapshot, StrategyContext


def _candle(close: float, volume: int = 1000, high: float | None = None, low: float | None = None) -> Candle:
    h = high if high is not None else close * 1.01
    l = low if low is not None else close * 0.99
    return Candle(
        interval="1h",
        time=datetime.now(timezone.utc),
        open=close,
        high=h,
        low=l,
        close=close,
        volume=volume,
    )


def _ctx(**kwargs) -> StrategyContext:
    defaults = dict(
        robot_id=1,
        cycle_id=uuid4(),
        config=StrategyConfig(
            archetype="momentum",
            timeframe="1h",
            params={"maPeriod": 20, "volumeMultiplier": 1.5, "breakoutLookback": 5},
        ),
        universe=["SBER"],
        last_price={"SBER": 100.0},
        candles={"SBER": [_candle(100 + i * 0.5, volume=1000 + i * 100) for i in range(30)]},
        atr={},
        open_positions=[],
        mode="paper",
        now=datetime.now(timezone.utc),
        triggered_by="bar_close",
    )
    defaults.update(kwargs)
    return StrategyContext(**defaults)


def test_all_archetypes_registered():
    items = list_archetypes()
    codes = {i.archetype for i in items}
    assert codes == {"scalper", "momentum", "reversion", "grid"}


def test_momentum_entry_on_breakout():
    candles = [_candle(90 + i, volume=2000) for i in range(25)]
    candles[-1] = _candle(120.0, volume=5000, high=121, low=119)
    ctx = _ctx(
        candles={"SBER": candles},
        last_price={"SBER": 120.0},
        triggered_by="bar_close",
    )
    runtime = StrategyRuntime()
    signals = runtime.evaluate(1, ctx)
    assert any(s.side == "BUY" and s.reason == "momentum_breakout" for s in signals)


def test_momentum_no_entry_on_poll():
    ctx = _ctx(triggered_by="poll")
    runtime = StrategyRuntime()
    signals = runtime.evaluate(2, ctx)
    assert not any(s.side == "BUY" for s in signals)
    scan = runtime.last_scan(2, "momentum")
    assert len(scan) == 1
    assert scan[0]["code"] == "WRONG_TRIGGER"
    assert scan[0]["metrics"]["triggeredBy"] == "poll"


def test_momentum_scan_warmup():
    ctx = _ctx(candles={"SBER": []}, triggered_by="bar_close")
    runtime = StrategyRuntime()
    runtime.evaluate(99, ctx)
    scan = runtime.last_scan(99, "momentum")
    assert scan and scan[0]["code"] == "WARMUP"


def test_momentum_exit_on_ma_cross():
    pos = Position(side="LONG", quantity=10, avg_entry_price=100, secid="SBER", current_price=95)
    ctx = _ctx(open_positions=[pos], last_price={"SBER": 95.0}, triggered_by="poll")
    runtime = StrategyRuntime()
    signals = runtime.evaluate(3, ctx)
    assert any(s.side == "CLOSE" and "momentum_ma_cross_down" in s.reason for s in signals)


def test_reversion_rsi_oversold_entry():
    # declining closes → low RSI
    candles = [_candle(100 - i * 2, volume=1000) for i in range(30)]
    ctx = _ctx(
        config=StrategyConfig(
            archetype="reversion",
            timeframe="1h",
            params={"indicator": "rsi", "overboughtThreshold": 80, "rsiPeriod": 14},
        ),
        candles={"SBER": candles},
        last_price={"SBER": candles[-1].close},
        triggered_by="bar_close",
    )
    runtime = StrategyRuntime()
    signals = runtime.evaluate(4, ctx)
    assert any(s.side == "BUY" for s in signals)


def test_scalper_requires_order_flow_on_price_tick():
    plugin = create_plugin("scalper")
    # No order-flow → no entry even on price_tick
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={"deltaThresholdPct": 5, "requiresWebSocket": True},
        ),
        ws_healthy=False,
        triggered_by="price_tick",
        order_flow=None,
    )
    assert plugin.evaluate(ctx) == []

    # REST fallback: ws unhealthy but price_tick + flow still allowed
    ctx.order_flow = {
        "SBER": OrderFlowSnapshot(
            buyVolume=5000,
            sellVolume=1000,
            deltaPct=50,
            windowSec=30,
            tickCount=5,
            tradeCount=4,
            hasRealTrades=True,
            flowSource="trades",
        ),
    }
    signals = plugin.evaluate(ctx)
    assert any(s.side == "BUY" for s in signals)

    # poll trigger never entries for scalper
    ctx.triggered_by = "poll"
    assert plugin.evaluate(ctx) == []


def test_scalper_delta_reversal_blocked_by_min_hold():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    opened = datetime.now(timezone.utc) - timedelta(seconds=5)
    pos = Position(
        side="LONG",
        quantity=10,
        avg_entry_price=100.0,
        secid="SBER",
        current_price=100.05,
        opened_at=opened,
    )
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={"deltaThresholdPct": 5, "minHoldSec": 30, "minExitMoveBps": 10},
        ),
        open_positions=[pos],
        last_price={"SBER": 100.05},
        triggered_by="price_tick",
        order_flow={
            "SBER": OrderFlowSnapshot(buyVolume=1000, sellVolume=9000, deltaPct=-8, windowSec=30),
        },
    )
    signals = plugin.evaluate(ctx)
    assert not any(s.side == "CLOSE" for s in signals)
    scan = plugin.last_scan or []
    assert any(row.get("code") == "EXIT_BLOCKED" for row in scan)


def test_scalper_delta_reversal_exits_after_hold_and_move():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    opened = datetime.now(timezone.utc) - timedelta(seconds=60)
    pos = Position(
        side="LONG",
        quantity=10,
        avg_entry_price=100.0,
        secid="SBER",
        current_price=102.0,
        opened_at=opened,
    )
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={"deltaThresholdPct": 5, "minHoldSec": 30, "minExitMoveBps": 10},
        ),
        open_positions=[pos],
        last_price={"SBER": 102.0},
        triggered_by="price_tick",
        take_profit_pct=1.0,
        order_flow={
            "SBER": OrderFlowSnapshot(buyVolume=1000, sellVolume=9000, deltaPct=-8, windowSec=30),
        },
    )
    signals = plugin.evaluate(ctx)
    assert any(s.side == "CLOSE" and s.reason == "scalper_delta_reversal" for s in signals)


def test_scalper_delta_reversal_blocked_below_break_even():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    opened = datetime.now(timezone.utc) - timedelta(seconds=60)
    pos = Position(
        side="LONG",
        quantity=10,
        avg_entry_price=322.6,
        secid="ROSN",
        current_price=322.3,
        opened_at=opened,
    )
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={
                "deltaThresholdPct": 5,
                "minHoldSec": 30,
                "minExitMoveBps": 5,
                "invalidateBelowEntryBps": 0,
            },
        ),
        open_positions=[pos],
        universe=["ROSN"],
        last_price={"ROSN": 322.3},
        triggered_by="price_tick",
        take_profit_pct=1.0,
        order_flow={
            "ROSN": OrderFlowSnapshot(buyVolume=1000, sellVolume=9000, deltaPct=-10, windowSec=30),
        },
    )
    signals = plugin.evaluate(ctx)
    assert not any(s.side == "CLOSE" for s in signals)
    scan = plugin.last_scan or []
    row = next(r for r in scan if r.get("ticker") == "ROSN")
    assert row.get("code") == "EXIT_BLOCKED"
    assert "безубыт" in str(row.get("message") or "").lower()


def test_scalper_delta_reversal_blocked_when_price_below_entry():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    opened = datetime.now(timezone.utc) - timedelta(seconds=60)
    pos = Position(
        side="LONG",
        quantity=10,
        avg_entry_price=1157.0,
        secid="PLZL",
        current_price=1155.8,
        opened_at=opened,
    )
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={
                "deltaThresholdPct": 5,
                "minHoldSec": 30,
                "minExitMoveBps": 10,
                "invalidateBelowEntryBps": 0,
            },
        ),
        open_positions=[pos],
        universe=["PLZL"],
        last_price={"PLZL": 1155.8},
        triggered_by="price_tick",
        order_flow={
            "PLZL": OrderFlowSnapshot(buyVolume=1000, sellVolume=9000, deltaPct=-16, windowSec=30),
        },
    )
    signals = plugin.evaluate(ctx)
    assert not any(s.side == "CLOSE" for s in signals)
    scan = plugin.last_scan or []
    assert any(row.get("code") == "EXIT_BLOCKED" for row in scan)
    blocked = next(r for r in scan if r.get("code") == "EXIT_BLOCKED")
    assert "Ждём" in str(blocked.get("message") or "")
    assert "безубыт" in str(blocked.get("message") or "").lower()


def test_scalper_invalidation_exits_below_break_even_after_adverse_move():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    opened = datetime.now(timezone.utc) - timedelta(seconds=120)
    pos = Position(
        side="LONG",
        quantity=10,
        avg_entry_price=100.0,
        secid="SBER",
        current_price=99.0,
        opened_at=opened,
    )
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={
                "deltaThresholdPct": 5,
                "minHoldSec": 90,
                "minExitMoveBps": 80,
                "invalidateBelowEntryBps": 80,
            },
        ),
        open_positions=[pos],
        universe=["SBER"],
        last_price={"SBER": 99.0},
        triggered_by="price_tick",
        broker_commission_rate=0.0005,
        order_flow={
            "SBER": OrderFlowSnapshot(buyVolume=1000, sellVolume=9000, deltaPct=-10, windowSec=30),
        },
    )
    signals = plugin.evaluate(ctx)
    assert any(s.side == "CLOSE" and s.reason == "scalper_delta_invalidation" for s in signals)


def test_scalper_invalidation_still_respects_min_hold():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    opened = datetime.now(timezone.utc) - timedelta(seconds=10)
    pos = Position(
        side="LONG",
        quantity=10,
        avg_entry_price=100.0,
        secid="SBER",
        current_price=99.0,
        opened_at=opened,
    )
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={
                "deltaThresholdPct": 5,
                "minHoldSec": 90,
                "minExitMoveBps": 80,
                "invalidateBelowEntryBps": 80,
            },
        ),
        open_positions=[pos],
        last_price={"SBER": 99.0},
        triggered_by="price_tick",
        order_flow={
            "SBER": OrderFlowSnapshot(buyVolume=1000, sellVolume=9000, deltaPct=-10, windowSec=30),
        },
    )
    signals = plugin.evaluate(ctx)
    assert not any(s.side == "CLOSE" for s in signals)
    row = next(r for r in (plugin.last_scan or []) if r.get("code") == "EXIT_BLOCKED")
    assert "удержание" in str(row.get("message") or "").lower()


def test_scalper_small_dip_below_be_does_not_invalidate():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    opened = datetime.now(timezone.utc) - timedelta(seconds=120)
    pos = Position(
        side="LONG",
        quantity=10,
        avg_entry_price=100.0,
        secid="SBER",
        current_price=99.50,
        opened_at=opened,
    )
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={
                "deltaThresholdPct": 5,
                "minHoldSec": 90,
                "minExitMoveBps": 80,
                "invalidateBelowEntryBps": 80,
            },
        ),
        open_positions=[pos],
        last_price={"SBER": 99.50},
        triggered_by="price_tick",
        broker_commission_rate=0.0005,
        order_flow={
            "SBER": OrderFlowSnapshot(buyVolume=1000, sellVolume=9000, deltaPct=-10, windowSec=30),
        },
    )
    signals = plugin.evaluate(ctx)
    assert not any(s.side == "CLOSE" for s in signals)
    row = next(r for r in (plugin.last_scan or []) if r.get("code") == "EXIT_BLOCKED")
    assert "безубыт" in str(row.get("message") or "").lower()


def test_allow_strategy_exit_below_break_even_only_invalidation():
    from app.modules.robots_v2.strategy.helpers import allow_strategy_exit_below_break_even

    assert allow_strategy_exit_below_break_even("scalper_delta_invalidation") is True
    assert allow_strategy_exit_below_break_even("scalper_delta_reversal") is False
    assert allow_strategy_exit_below_break_even("take_profit") is False


def test_scalper_in_position_explains_wait_and_readings():
    plugin = create_plugin("scalper")
    pos = Position(
        side="LONG",
        quantity=10,
        avg_entry_price=100.0,
        secid="SBER",
        current_price=100.05,
    )
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={"deltaThresholdPct": 8, "minHoldSec": 90, "minExitMoveBps": 80},
        ),
        open_positions=[pos],
        last_price={"SBER": 100.05},
        triggered_by="price_tick",
        take_profit_pct=1.5,
        stop_loss_pct=0.6,
        broker_commission_rate=0.0005,
        tax_pct=13,
        order_flow={
            "SBER": OrderFlowSnapshot(buyVolume=5000, sellVolume=5000, deltaPct=0.0, windowSec=30),
        },
    )
    signals = plugin.evaluate(ctx)
    assert not any(s.side == "CLOSE" for s in signals)
    row = next(r for r in (plugin.last_scan or []) if r.get("ticker") == "SBER")
    assert row.get("code") == "IN_POSITION"
    msg = str(row.get("message") or "")
    assert "Ждём" in msg
    assert "разворот delta" in msg
    assert "delta +0.0%" in msg
    assert "безубыток" in msg
    assert "TP" in msg
    assert "SL" in msg


def test_scalper_delta_reversal_allows_above_break_even_below_take_profit():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    opened = datetime.now(timezone.utc) - timedelta(seconds=60)
    pos = Position(
        side="LONG",
        quantity=10,
        avg_entry_price=100.0,
        secid="SBER",
        current_price=100.20,
        opened_at=opened,
    )
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={"deltaThresholdPct": 5, "minHoldSec": 30, "minExitMoveBps": 10},
        ),
        open_positions=[pos],
        universe=["SBER"],
        last_price={"SBER": 100.20},
        triggered_by="price_tick",
        take_profit_pct=1.0,
        broker_commission_rate=0.0005,
        order_flow={
            "SBER": OrderFlowSnapshot(buyVolume=1000, sellVolume=9000, deltaPct=-10, windowSec=30),
        },
    )
    signals = plugin.evaluate(ctx)
    assert any(s.side == "CLOSE" and s.reason == "scalper_delta_reversal" for s in signals)


def test_scalper_blocks_thin_one_sided_inferred_flow():
    """PLZL-style +100% delta from 2 upticks must not trigger entry."""
    plugin = create_plugin("scalper")
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={"deltaThresholdPct": 5, "requiresWebSocket": True},
        ),
        universe=["PLZL"],
        last_price={"PLZL": 1157.0},
        triggered_by="price_tick",
        order_flow={
            "PLZL": OrderFlowSnapshot(
                buyVolume=2314.0,
                sellVolume=0.0,
                deltaPct=100.0,
                windowSec=30,
                tickCount=2,
                tradeCount=0,
                hasRealTrades=False,
                flowSource="inferred",
            ),
        },
    )
    signals = plugin.evaluate(ctx)
    assert not any(s.side == "BUY" for s in signals)
    scan = plugin.last_scan or []
    row = next(r for r in scan if r.get("ticker") == "PLZL")
    assert row.get("code") == "THIN_ORDER_FLOW"
    assert row.get("metrics", {}).get("buyVolume") == 2314.0
    assert row.get("metrics", {}).get("sellVolume") == 0.0
    assert row.get("metrics", {}).get("hasRealTrades") is False


def test_scalper_scan_includes_flow_metrics():
    plugin = create_plugin("scalper")
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={"deltaThresholdPct": 5},
        ),
        universe=["SBER"],
        last_price={"SBER": 100.0},
        triggered_by="price_tick",
        order_flow={
            "SBER": OrderFlowSnapshot(
                buyVolume=2000,
                sellVolume=500,
                deltaPct=60,
                windowSec=30,
                tickCount=4,
                tradeCount=0,
                hasRealTrades=False,
                flowSource="inferred",
            ),
        },
    )
    plugin.evaluate(ctx)
    scan = plugin.last_scan or []
    row = next(r for r in scan if r.get("ticker") == "SBER")
    metrics = row.get("metrics", {})
    assert metrics.get("buyVolume") == 2000.0
    assert metrics.get("sellVolume") == 500.0
    assert metrics.get("tickCount") == 4
    assert metrics.get("hasRealTrades") is False
    assert metrics.get("flowSource") == "inferred"


def test_scalper_blocks_entry_after_stop_loss_cooldown():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    now = datetime.now(timezone.utc)
    plugin.on_stop_loss("SMLT", at=now - timedelta(seconds=60))
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={"deltaThresholdPct": 5, "stopLossCooldownSec": 300},
        ),
        universe=["SMLT"],
        last_price={"SMLT": 380.0},
        triggered_by="price_tick",
        now=now,
        order_flow={
            "SMLT": OrderFlowSnapshot(
                buyVolume=5000,
                sellVolume=1000,
                deltaPct=50,
                windowSec=30,
                tickCount=5,
                hasRealTrades=True,
                flowSource="trades",
            ),
        },
    )
    assert plugin.evaluate(ctx) == []
    scan = plugin.last_scan or []
    assert any(row.get("code") == "SL_COOLDOWN" for row in scan)


def _scalper_buy_flow() -> OrderFlowSnapshot:
    return OrderFlowSnapshot(
        buyVolume=5000,
        sellVolume=1000,
        deltaPct=50,
        windowSec=30,
        tickCount=5,
        hasRealTrades=True,
        flowSource="trades",
    )


def test_scalper_invalidation_sets_sl_cooldown_on_same_plugin():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    now = datetime.now(timezone.utc)
    opened = now - timedelta(seconds=120)
    pos = Position(
        side="LONG",
        quantity=10,
        avg_entry_price=100.0,
        secid="SMLT",
        current_price=98.0,
        opened_at=opened,
    )
    close_ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={
                "deltaThresholdPct": 5,
                "minHoldSec": 90,
                "minExitMoveBps": 80,
                "invalidateBelowEntryBps": 80,
                "stopLossCooldownSec": 300,
            },
        ),
        universe=["SMLT"],
        open_positions=[pos],
        last_price={"SMLT": 98.0},
        triggered_by="price_tick",
        now=now,
        broker_commission_rate=0.0005,
        order_flow={
            "SMLT": OrderFlowSnapshot(buyVolume=1000, sellVolume=9000, deltaPct=-12, windowSec=30),
        },
    )
    signals = plugin.evaluate(close_ctx)
    assert any(s.side == "CLOSE" and s.reason == "scalper_delta_invalidation" for s in signals)

    entry_ctx = _ctx(
        config=close_ctx.config,
        universe=["SMLT"],
        last_price={"SMLT": 99.5},
        triggered_by="price_tick",
        now=now + timedelta(seconds=60),
        order_flow={"SMLT": _scalper_buy_flow()},
    )
    assert plugin.evaluate(entry_ctx) == []
    assert any(row.get("code") == "SL_COOLDOWN" for row in (plugin.last_scan or []))


def test_scalper_blocks_long_below_last_invalidation_price():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    now = datetime.now(timezone.utc)
    plugin.ticker_state("SMLT")["lastCutPrice"] = 371.4
    plugin.ticker_state("SMLT")["lastSlAt"] = now - timedelta(seconds=700)
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={"deltaThresholdPct": 5, "stopLossCooldownSec": 300},
        ),
        universe=["SMLT"],
        last_price={"SMLT": 368.0},
        triggered_by="price_tick",
        now=now,
        order_flow={"SMLT": _scalper_buy_flow()},
    )
    assert plugin.evaluate(ctx) == []
    assert any(row.get("code") == "BELOW_CUT" for row in (plugin.last_scan or []))


def test_scalper_allows_long_after_reclaiming_cut_price():
    from datetime import timedelta

    plugin = create_plugin("scalper")
    now = datetime.now(timezone.utc)
    plugin.ticker_state("SMLT")["lastCutPrice"] = 371.4
    plugin.ticker_state("SMLT")["lastSlAt"] = now - timedelta(seconds=700)
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={"deltaThresholdPct": 5, "stopLossCooldownSec": 300},
        ),
        universe=["SMLT"],
        last_price={"SMLT": 372.0},
        triggered_by="price_tick",
        now=now,
        order_flow={"SMLT": _scalper_buy_flow()},
    )
    signals = plugin.evaluate(ctx)
    assert any(s.side == "BUY" and s.reason == "scalper_delta_cross" for s in signals)


def test_scalper_blocks_long_in_downtrend():
    plugin = create_plugin("scalper")
    ts = plugin.ticker_state("SMLT")
    ts["priceHist"] = [400.0, 399.0, 398.0, 397.0, 396.0]
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={
                "deltaThresholdPct": 5,
                "trendLookbackTicks": 5,
                "trendBlockLongBps": 30,
            },
        ),
        universe=["SMLT"],
        last_price={"SMLT": 396.0},
        triggered_by="price_tick",
        order_flow={
            "SMLT": OrderFlowSnapshot(
                buyVolume=5000,
                sellVolume=1000,
                deltaPct=50,
                windowSec=30,
                tickCount=5,
                hasRealTrades=True,
                flowSource="trades",
            ),
        },
    )
    assert plugin.evaluate(ctx) == []
    scan = plugin.last_scan or []
    assert any(row.get("code") == "TREND_DOWN" for row in scan)


def test_grid_initial_entry():
    plugin = create_plugin("grid")
    ctx = _ctx(
        config=StrategyConfig(
            archetype="grid",
            timeframe="15m",
            params={"gridStepAtrPct": 2, "gridDepth": 5},
        ),
        atr={"SBER": 5.0},
        last_price={"SBER": 100.0},
        triggered_by="price_tick",
    )
    signals = plugin.evaluate(ctx)
    assert any(s.reason == "grid_level_0" for s in signals)


def test_exits_before_entries_ordering():
    runtime = StrategyRuntime()
    pos = Position(side="LONG", quantity=5, avg_entry_price=100, secid="SBER")
    candles = [_candle(100 - i, volume=1000) for i in range(30)]
    ctx = _ctx(
        config=StrategyConfig(
            archetype="reversion",
            timeframe="1h",
            params={"indicator": "rsi", "overboughtThreshold": 70, "rsiPeriod": 14},
        ),
        open_positions=[pos],
        candles={"SBER": candles},
        last_price={"SBER": candles[-1].close},
        triggered_by="bar_close",
    )
    signals = runtime.evaluate(5, ctx)
    if len(signals) >= 2:
        first_close_idx = next((i for i, s in enumerate(signals) if s.side == "CLOSE"), None)
        first_buy_idx = next((i for i, s in enumerate(signals) if s.side == "BUY"), None)
        if first_close_idx is not None and first_buy_idx is not None:
            assert first_close_idx < first_buy_idx
