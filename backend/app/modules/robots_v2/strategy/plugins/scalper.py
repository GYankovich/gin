"""Scalper archetype — order-flow delta on price ticks."""

from __future__ import annotations

from datetime import timedelta

from app.modules.robots.trading.contracts import Signal
from app.modules.robots_v2.config.v4_schema import ScalperParams
from app.modules.robots_v2.strategy.base import StrategyPlugin
from app.modules.robots_v2.strategy.helpers import has_open_position, make_entry_signal, make_exit_signal
from app.modules.robots_v2.strategy.schemas import StrategyContext

MIN_ORDER_FLOW_LIQUIDITY = 1_000.0


class ScalperPlugin(StrategyPlugin):
    archetype = "scalper"
    required_data = ["last_price", "websocket_trades", "orderbook_delta"]
    warmup_bars = 0
    entry_triggers = ["price_tick"]

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        if not ctx.ws_healthy:
            return []
        params = ScalperParams.model_validate(ctx.config.params)
        signals: list[Signal] = []
        exits: list[Signal] = []
        entries: list[Signal] = []

        for ticker in ctx.universe:
            t = ticker.upper()
            if not self._in_universe(ctx, t):
                continue
            pos = has_open_position(ctx.open_positions, t)
            flow = (ctx.order_flow or {}).get(t)
            price = ctx.last_price.get(t)
            ts = self.ticker_state(t)

            if pos is not None:
                if flow is not None and pos.side == "LONG" and flow.delta_pct <= -params.delta_threshold_pct:
                    exits.append(make_exit_signal(ticker=t, reason="scalper_delta_reversal", price=price))
                elif flow is not None and pos.side == "SHORT" and flow.delta_pct >= params.delta_threshold_pct:
                    exits.append(make_exit_signal(ticker=t, reason="scalper_delta_reversal", price=price))
                continue

            if ctx.triggered_by != "price_tick" or flow is None or price is None:
                continue

            last_trade_at = ts.get("lastTradeAt")
            if last_trade_at is not None:
                cooldown = timedelta(seconds=params.cooldown_sec)
                if ctx.now - last_trade_at < cooldown:
                    continue

            liquidity = flow.buy_volume + flow.sell_volume
            if liquidity < MIN_ORDER_FLOW_LIQUIDITY:
                continue

            if flow.delta_pct >= params.delta_threshold_pct:
                entries.append(make_entry_signal(
                    ticker=t, side="BUY", reason="scalper_delta_cross", price=price,
                    strength=min(1.0, abs(flow.delta_pct) / max(params.delta_threshold_pct, 1)),
                ))
                ts["lastTradeAt"] = ctx.now
                ts["lastDelta"] = flow.delta_pct
            elif ctx.allow_short and flow.delta_pct <= -params.delta_threshold_pct:
                entries.append(make_entry_signal(
                    ticker=t, side="SELL", reason="scalper_delta_cross", price=price,
                    strength=min(1.0, abs(flow.delta_pct) / max(params.delta_threshold_pct, 1)),
                ))
                ts["lastTradeAt"] = ctx.now
                ts["lastDelta"] = flow.delta_pct

        # One entry per ticker per cycle — already enforced by loop structure
        signals.extend(exits)
        signals.extend(entries)
        return signals
