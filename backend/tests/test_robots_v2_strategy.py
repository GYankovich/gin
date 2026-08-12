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


def test_scalper_requires_ws_and_order_flow():
    plugin = create_plugin("scalper")
    ctx = _ctx(
        config=StrategyConfig(
            archetype="scalper",
            timeframe="1m",
            params={"deltaThresholdPct": 5, "requiresWebSocket": True},
        ),
        ws_healthy=False,
        triggered_by="price_tick",
        order_flow={"SBER": OrderFlowSnapshot(buyVolume=5000, sellVolume=1000, deltaPct=50, windowSec=30)},
    )
    assert plugin.evaluate(ctx) == []

    ctx.ws_healthy = True
    signals = plugin.evaluate(ctx)
    assert any(s.side == "BUY" for s in signals)


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
