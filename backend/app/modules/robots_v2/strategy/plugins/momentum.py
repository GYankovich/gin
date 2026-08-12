"""Momentum archetype — MA + breakout + volume confirmation."""

from __future__ import annotations

from app.modules.robots.trading.contracts import Signal
from app.modules.robots_v2.config.v4_schema import MomentumParams
from app.modules.robots_v2.strategy.base import StrategyPlugin
from app.modules.robots_v2.strategy.helpers import has_open_position, make_entry_signal, make_exit_signal
from app.modules.robots_v2.strategy.indicators import (
    breakout_high,
    last_close,
    last_volume,
    sma_close,
    sma_volume,
)
from app.modules.robots_v2.strategy.schemas import StrategyContext


class MomentumPlugin(StrategyPlugin):
    archetype = "momentum"
    required_data = ["candles", "bar_close_events", "last_price"]
    warmup_bars = 0  # computed dynamically from params
    entry_triggers = ["bar_close", "poll"]

    def warmup_bars_for(self, params: MomentumParams) -> int:
        return params.ma_period + params.breakout_lookback

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        params = MomentumParams.model_validate(ctx.config.params)
        warmup = self.warmup_bars_for(params)
        exits: list[Signal] = []
        entries: list[Signal] = []

        for ticker in ctx.universe:
            t = ticker.upper()
            candles = ctx.candles.get(t) or []
            if not self._warmup_ok(candles, t) and len(candles) < warmup:
                continue
            price = ctx.last_price.get(t) or last_close(candles)
            pos = has_open_position(ctx.open_positions, t)
            ma = sma_close(candles, params.ma_period)
            if ma is None or price is None:
                continue

            if pos is not None:
                if pos.side == "LONG" and price < ma:
                    exits.append(make_exit_signal(ticker=t, reason="momentum_ma_cross_down", price=price))
                continue

            if ctx.triggered_by != "bar_close":
                continue

            brk = breakout_high(candles, params.breakout_lookback)
            avg_vol = sma_volume(candles, params.ma_period)
            vol = last_volume(candles)
            if brk is None or avg_vol is None:
                continue
            if price > ma and price > brk and vol >= avg_vol * params.volume_multiplier:
                entries.append(make_entry_signal(
                    ticker=t, side="BUY", reason="momentum_breakout", price=price,
                ))

        return exits + entries
