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
        self._begin_scan()

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
            pos = has_open_position(ctx.open_positions, t)
            ma = sma_close(candles, params.ma_period)
            if ma is None or price is None:
                self._record_scan(
                    t,
                    code="NO_DATA",
                    message="Нет цены или MA",
                    price=price,
                    metrics={"bars": bars, "ma": ma},
                )
                continue

            if pos is not None:
                if pos.side == "LONG" and price < ma:
                    exits.append(make_exit_signal(ticker=t, reason="momentum_ma_cross_down", price=price))
                    self._record_scan(
                        t,
                        code="EXIT_SIGNAL",
                        message=f"Выход: цена {price:.2f} < MA {ma:.2f}",
                        price=price,
                        metrics={"ma": round(ma, 4), "bars": bars},
                    )
                else:
                    self._record_scan(
                        t,
                        code="IN_POSITION",
                        message=f"В позиции, цена {price:.2f}, MA {ma:.2f}",
                        price=price,
                        metrics={"ma": round(ma, 4), "side": pos.side, "bars": bars},
                    )
                continue

            if ctx.triggered_by != "bar_close":
                self._record_scan(
                    t,
                    code="WRONG_TRIGGER",
                    message=f"Вход только на закрытии бара (сейчас {ctx.triggered_by})",
                    price=price,
                    metrics={"ma": round(ma, 4), "bars": bars, "triggeredBy": ctx.triggered_by},
                )
                continue

            brk = breakout_high(candles, params.breakout_lookback)
            avg_vol = sma_volume(candles, params.ma_period)
            vol = last_volume(candles)
            if brk is None or avg_vol is None:
                self._record_scan(
                    t,
                    code="NO_INDICATORS",
                    message="Недостаточно данных для breakout/объёма",
                    price=price,
                    metrics={"ma": round(ma, 4), "bars": bars},
                )
                continue

            vol_threshold = avg_vol * params.volume_multiplier
            metrics = {
                "ma": round(ma, 4),
                "breakout": round(brk, 4),
                "volume": round(float(vol or 0), 0),
                "avgVolume": round(float(avg_vol), 0),
                "volumeThreshold": round(float(vol_threshold), 0),
                "bars": bars,
            }
            if price <= ma:
                self._record_scan(
                    t,
                    code="BELOW_MA",
                    message=f"Цена {price:.2f} ≤ MA {ma:.2f}",
                    price=price,
                    metrics=metrics,
                )
                continue
            if price <= brk:
                self._record_scan(
                    t,
                    code="BELOW_BREAKOUT",
                    message=f"Цена {price:.2f} ≤ breakout {brk:.2f}",
                    price=price,
                    metrics=metrics,
                )
                continue
            if vol < vol_threshold:
                self._record_scan(
                    t,
                    code="LOW_VOLUME",
                    message=f"Объём {vol:.0f} < порог {vol_threshold:.0f}",
                    price=price,
                    metrics=metrics,
                )
                continue

            entries.append(make_entry_signal(
                ticker=t, side="BUY", reason="momentum_breakout", price=price,
            ))
            self._record_scan(
                t,
                code="SIGNAL",
                message="Сформирован сигнал на вход (breakout + объём)",
                price=price,
                metrics=metrics,
            )

        return exits + entries
