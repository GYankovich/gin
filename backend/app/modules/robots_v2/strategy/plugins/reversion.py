"""Reversion archetype — RSI / stochastic mean-reversion."""

from __future__ import annotations

from app.modules.robots.trading.contracts import Signal
from app.modules.robots_v2.config.v4_schema import ReversionParams
from app.modules.robots_v2.strategy.base import StrategyPlugin
from app.modules.robots_v2.strategy.helpers import has_open_position, make_entry_signal, make_exit_signal
from app.modules.robots_v2.strategy.indicators import last_close, rsi_value, stochastic_k
from app.modules.robots_v2.strategy.schemas import StrategyContext


class ReversionPlugin(StrategyPlugin):
    archetype = "reversion"
    required_data = ["candles", "bar_close_events"]
    warmup_bars = 0
    entry_triggers = ["bar_close", "poll"]

    def warmup_bars_for(self, params: ReversionParams) -> int:
        return params.rsi_period + 5

    def _indicator_value(self, params: ReversionParams, candles: list) -> float | None:
        if params.indicator == "rsi":
            return rsi_value(candles, params.rsi_period)
        if params.indicator == "stochastic":
            return stochastic_k(candles, params.rsi_period)
        return None  # divergence — MVP+

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        params = ReversionParams.model_validate(ctx.config.params)
        if params.indicator == "divergence":
            return []

        warmup = self.warmup_bars_for(params)
        exits: list[Signal] = []
        entries: list[Signal] = []

        for ticker in ctx.universe:
            t = ticker.upper()
            candles = ctx.candles.get(t) or []
            if len(candles) < warmup:
                continue
            price = ctx.last_price.get(t) or last_close(candles)
            indicator = self._indicator_value(params, candles)
            if indicator is None or price is None:
                continue

            ts = self.ticker_state(t)
            ts["lastRsi"] = indicator
            pos = has_open_position(ctx.open_positions, t)

            if pos is not None:
                if pos.side == "LONG":
                    if indicator >= params.overbought_threshold:
                        exits.append(make_exit_signal(ticker=t, reason="reversion_rsi_target", price=price))
                    elif indicator < 50:
                        exits.append(make_exit_signal(ticker=t, reason="reversion_rsi_fail", price=price))
                continue

            if ctx.triggered_by != "bar_close":
                continue

            if indicator <= (params.oversold_threshold or 20):
                entries.append(make_entry_signal(
                    ticker=t, side="BUY", reason="reversion_rsi_oversold", price=price,
                ))
            elif ctx.allow_short and indicator >= params.overbought_threshold:
                entries.append(make_entry_signal(
                    ticker=t, side="SELL", reason="reversion_rsi_overbought", price=price,
                ))

        return exits + entries
