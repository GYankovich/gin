"""Grid archetype — virtual levels, single position per ticker."""

from __future__ import annotations

from app.modules.robots.trading.contracts import Signal
from app.modules.robots_v2.config.v4_schema import GridParams
from app.modules.robots_v2.strategy.base import StrategyPlugin
from app.modules.robots_v2.strategy.helpers import has_open_position, make_entry_signal, make_exit_signal
from app.modules.robots_v2.strategy.indicators import atr_value, last_close
from app.modules.robots_v2.strategy.schemas import StrategyContext


class GridPlugin(StrategyPlugin):
    archetype = "grid"
    required_data = ["candles", "atr", "last_price"]
    warmup_bars = 19
    entry_triggers = ["price_tick", "poll"]

    def _grid_step(self, ctx: StrategyContext, ticker: str, params: GridParams) -> float | None:
        atr = ctx.atr.get(ticker.upper())
        if atr is None:
            candles = ctx.candles.get(ticker.upper()) or []
            atr = atr_value(candles, 14)
        if atr is None or atr <= 0:
            return None
        return atr * (params.grid_step_atr_pct / 100.0)

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        params = GridParams.model_validate(ctx.config.params)
        exits: list[Signal] = []
        entries: list[Signal] = []
        self._begin_scan()

        for ticker in ctx.universe:
            t = ticker.upper()
            candles = ctx.candles.get(t) or []
            bars = len(candles)
            if bars < self.warmup_bars:
                self._record_scan(
                    t,
                    code="WARMUP",
                    message=f"Прогрев: {bars}/{self.warmup_bars} баров",
                    price=ctx.last_price.get(t),
                    metrics={"bars": bars, "warmup": self.warmup_bars},
                )
                continue
            price = ctx.last_price.get(t) or last_close(candles)
            if price is None:
                self._record_scan(t, code="NO_PRICE", message="Нет цены")
                continue
            step = self._grid_step(ctx, t, params)
            if step is None or step <= 0:
                self._record_scan(
                    t,
                    code="NO_ATR",
                    message="ATR = 0 — нельзя построить сетку",
                    price=price,
                    metrics={"bars": bars},
                )
                continue

            pos = has_open_position(ctx.open_positions, t)
            gs = self.ticker_state(t)
            metrics = {"bars": bars, "gridStep": round(step, 4), "price": round(price, 4)}

            if pos is None and not gs.get("anchorPrice"):
                entries.append(make_entry_signal(
                    ticker=t,
                    side="BUY",
                    reason="grid_level_0",
                    price=price,
                    strength=params.base_allocation_pct / 100.0,
                ))
                gs.update({
                    "anchorPrice": price,
                    "filledLevels": 0,
                    "nextLevelPrice": price - step,
                    "direction": "long",
                })
                self._record_scan(
                    t, code="SIGNAL",
                    message="Сигнал: старт сетки (level 0)",
                    price=price, metrics=metrics,
                )
                continue

            if pos is None:
                self._record_scan(
                    t,
                    code="NO_ANCHOR",
                    message="Нет позиции и anchor — ожидание level 0",
                    price=price,
                    metrics=metrics,
                )
                continue

            anchor = float(gs.get("anchorPrice") or pos.avg_entry_price)
            filled = int(gs.get("filledLevels") or 0)
            next_level = float(gs.get("nextLevelPrice") or anchor - step)
            metrics.update({
                "anchor": round(anchor, 4),
                "filledLevels": filled,
                "nextLevel": round(next_level, 4),
            })

            if price >= anchor + step:
                exits.append(make_exit_signal(
                    ticker=t, reason="grid_tp", price=price, kind="exit_grid",
                ))
                gs.clear()
                self._record_scan(
                    t, code="EXIT_SIGNAL",
                    message=f"Take-profit: цена {price:.2f} ≥ anchor+step {anchor + step:.2f}",
                    price=price, metrics=metrics,
                )
                continue

            if filled < params.grid_depth and price <= next_level:
                level = filled + 1
                scale = params.scale_multiplier ** level
                entries.append(make_entry_signal(
                    ticker=t,
                    side="BUY",
                    reason=f"grid_level_{level}",
                    price=price,
                    strength=min(1.0, (params.base_allocation_pct / 100.0) * scale),
                ))
                gs["filledLevels"] = level
                gs["nextLevelPrice"] = next_level - step
                self._record_scan(
                    t, code="SIGNAL",
                    message=f"Сигнал: grid level {level}, цена ≤ {next_level:.2f}",
                    price=price, metrics=metrics,
                )
            else:
                self._record_scan(
                    t,
                    code="IN_POSITION",
                    message=(
                        f"В сетке: level {filled}, цена {price:.2f}, "
                        f"след. уровень {next_level:.2f}"
                    ),
                    price=price,
                    metrics=metrics,
                )

        return exits + entries
