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

    def _indicator_value(
        self,
        params: ReversionParams,
        candles: list,
        ticker_state: dict,
    ) -> float | None:
        if params.indicator == "rsi":
            return rsi_value(candles, params.rsi_period, state=ticker_state)
        if params.indicator == "stochastic":
            return stochastic_k(candles, params.rsi_period)
        return None  # divergence — MVP+

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        params = ReversionParams.model_validate(ctx.config.params)
        self._begin_scan()
        if params.indicator == "divergence":
            for ticker in ctx.universe:
                self._record_scan(
                    ticker.upper(),
                    code="UNSUPPORTED",
                    message="Индикатор divergence пока не поддержан",
                    price=ctx.last_price.get(ticker.upper()),
                )
            return []

        warmup = self.warmup_bars_for(params)
        exits: list[Signal] = []
        entries: list[Signal] = []

        for ticker in ctx.universe:
            t = ticker.upper()
            candles = ctx.candles.get(t) or []
            bars = len(candles)
            if bars < warmup:
                self._record_scan(
                    t,
                    code="WARMUP",
                    message=f"Прогрев: {bars}/{warmup} баров",
                    price=ctx.last_price.get(t),
                    metrics={"bars": bars, "warmup": warmup},
                )
                continue
            price = ctx.last_price.get(t) or last_close(candles)
            ts = self.ticker_state(t)
            indicator = self._indicator_value(params, candles, ts)
            if indicator is None or price is None:
                self._record_scan(
                    t,
                    code="NO_DATA",
                    message="Нет цены или значения индикатора",
                    price=price,
                    metrics={"bars": bars, "indicator": params.indicator},
                )
                continue

            ts["lastRsi"] = indicator
            pos = has_open_position(ctx.open_positions, t)
            metrics = {
                "bars": bars,
                params.indicator: round(float(indicator), 2),
                "oversold": params.oversold_threshold or 20,
                "overbought": params.overbought_threshold,
            }

            if pos is not None:
                if pos.side == "LONG":
                    # Hold through oversold climb; take profit at mid (50) or overbought.
                    # Do NOT cut merely because RSI < 50 — that is the normal post-entry state.
                    if indicator >= params.overbought_threshold:
                        exits.append(make_exit_signal(ticker=t, reason="reversion_rsi_target", price=price))
                        self._record_scan(
                            t, code="EXIT_SIGNAL",
                            message=f"Выход: {params.indicator}={indicator:.1f} ≥ {params.overbought_threshold}",
                            price=price, metrics=metrics,
                        )
                    elif indicator >= 50:
                        exits.append(make_exit_signal(ticker=t, reason="reversion_rsi_mean", price=price))
                        self._record_scan(
                            t, code="EXIT_SIGNAL",
                            message=f"Выход: mean — {params.indicator}={indicator:.1f} ≥ 50",
                            price=price, metrics=metrics,
                        )
                    else:
                        self._record_scan(
                            t, code="IN_POSITION",
                            message=f"В позиции, {params.indicator}={indicator:.1f}",
                            price=price, metrics=metrics,
                        )
                continue

            if ctx.triggered_by != "bar_close":
                self._record_scan(
                    t,
                    code="WRONG_TRIGGER",
                    message=f"Вход только на закрытии бара (сейчас {ctx.triggered_by})",
                    price=price,
                    metrics={**metrics, "triggeredBy": ctx.triggered_by},
                )
                continue

            if indicator <= (params.oversold_threshold or 20):
                entries.append(make_entry_signal(
                    ticker=t, side="BUY", reason="reversion_rsi_oversold", price=price,
                ))
                self._record_scan(
                    t, code="SIGNAL",
                    message=f"Сигнал BUY: {params.indicator}={indicator:.1f} ≤ oversold",
                    price=price, metrics=metrics,
                )
            elif ctx.allow_short and indicator >= params.overbought_threshold:
                entries.append(make_entry_signal(
                    ticker=t, side="SELL", reason="reversion_rsi_overbought", price=price,
                ))
                self._record_scan(
                    t, code="SIGNAL",
                    message=f"Сигнал SELL: {params.indicator}={indicator:.1f} ≥ overbought",
                    price=price, metrics=metrics,
                )
            else:
                self._record_scan(
                    t,
                    code="NO_ENTRY",
                    message=(
                        f"{params.indicator}={indicator:.1f} вне зон входа "
                        f"(oversold≤{params.oversold_threshold or 20}, "
                        f"overbought≥{params.overbought_threshold})"
                    ),
                    price=price,
                    metrics=metrics,
                )

        return exits + entries
