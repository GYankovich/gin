"""Scalper archetype — order-flow delta on price ticks."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from app.modules.robots.trading.contracts import Position, Signal
from app.modules.robots.trading.costs import (
    calculate_break_even_price,
    calculate_stop_loss_price,
    calculate_take_profit_price,
)
from app.modules.robots.trading.risk.manager import should_skip_take_profit
from app.modules.robots_v2.config.v4_schema import ScalperParams
from app.modules.robots_v2.strategy.base import StrategyPlugin
from app.modules.robots_v2.strategy.helpers import block_exit_below_break_even, has_open_position, make_entry_signal, make_exit_signal
from app.modules.robots_v2.strategy.schemas import OrderFlowSnapshot, StrategyContext

MIN_ORDER_FLOW_LIQUIDITY = 1_000.0


def _flow_metrics(flow: OrderFlowSnapshot, **extra: Any) -> dict[str, Any]:
    return {
        "deltaPct": round(flow.delta_pct, 2),
        "buyVolume": round(flow.buy_volume, 0),
        "sellVolume": round(flow.sell_volume, 0),
        "tickCount": flow.tick_count,
        "tradeCount": flow.trade_count,
        "hasRealTrades": flow.has_real_trades,
        "flowSource": flow.flow_source,
        **extra,
    }


def _entry_flow_gate(flow: OrderFlowSnapshot, params: ScalperParams) -> str | None:
    """Block entry when delta is driven by too few inferred ticks (e.g. +100% on 2 upticks)."""
    if flow.tick_count < params.min_flow_ticks:
        return f"tick_count {flow.tick_count} < {params.min_flow_ticks}"

    if flow.has_real_trades:
        return None

    buy, sell = flow.buy_volume, flow.sell_volume
    one_sided = (buy > 0 and sell <= 0) or (sell > 0 and buy <= 0)
    if one_sided and flow.tick_count < 5:
        return "one_sided_inferred"
    if abs(flow.delta_pct) >= 90 and flow.tick_count < 5:
        return "extreme_delta_inferred"
    return None


def _update_price_history(ts: dict[str, Any], price: float, max_len: int) -> None:
    if max_len <= 0:
        return
    hist: list[float] = ts.setdefault("priceHist", [])
    hist.append(float(price))
    if len(hist) > max_len:
        ts["priceHist"] = hist[-max_len:]


def _trend_bps(ts: dict[str, Any]) -> float | None:
    hist: list[float] = ts.get("priceHist") or []
    if len(hist) < 2:
        return None
    start, end = hist[0], hist[-1]
    if start <= 0:
        return None
    return (end - start) / start * 10000.0


def _sl_cooldown_block(ts: dict[str, Any], params: ScalperParams, now: Any) -> str | None:
    last_sl = ts.get("lastSlAt")
    if last_sl is None or params.stop_loss_cooldown_sec <= 0:
        return None
    elapsed = (now - last_sl).total_seconds()
    if elapsed < params.stop_loss_cooldown_sec:
        remain = int(params.stop_loss_cooldown_sec - elapsed)
        return f"stop_loss_cooldown {remain}s left"
    return None


def _trend_block_long(ts: dict[str, Any], params: ScalperParams) -> str | None:
    if params.trend_lookback_ticks <= 0:
        return None
    trend = _trend_bps(ts)
    if trend is None:
        return None
    if trend <= -float(params.trend_block_long_bps):
        return f"downtrend {trend:.1f}bps"
    return None


def _exit_guard_reason(
    pos: Position,
    *,
    price: float | None,
    params: ScalperParams,
    now: Any,
    take_profit_pct: float | None = None,
    broker_commission_rate: float | None = None,
    tax_pct: float | None = None,
) -> str | None:
    """Block delta-reversal exit until min hold + min move + break-even floor."""
    if price is None or float(price) <= 0:
        return "no_price"
    entry = float(pos.avg_entry_price or 0)
    side = str(getattr(pos, "side", "") or "LONG")
    if entry > 0:
        tp_block = block_exit_below_break_even(
            entry=entry,
            price=float(price),
            side=side,
            broker_commission_rate=broker_commission_rate,
        )
        if tp_block:
            return tp_block
    pos_dict = {
        "entry_price": entry,
        "opened_at": getattr(pos, "opened_at", None),
        "created_at": getattr(pos, "opened_at", None),
        "side": side,
    }
    risk_like = {
        "min_hold_seconds": float(params.min_hold_sec),
        "min_tp_move_bps": float(params.min_exit_move_bps),
    }
    return should_skip_take_profit(
        pos_dict,
        current_price=float(price),
        risk_params=risk_like,
        now=now,
        require_favorable_move=True,
    )


def _humanize_exit_guard(block: str) -> str:
    if block.startswith("below_break_even"):
        m = re.search(r"price=([\d.]+)<be=([\d.]+)", block)
        if m:
            return f"цена {m.group(1)} ниже безубытка {m.group(2)} — стратегию не продаём"
        return "цена ниже безубытка — стратегию не продаём"
    if block.startswith("above_break_even"):
        m = re.search(r"price=([\d.]+)>be=([\d.]+)", block)
        if m:
            return f"цена {m.group(1)} выше безубытка {m.group(2)} — стратегию не закрываем short"
        return "цена выше безубытка short — стратегию не закрываем"
    if "min_hold_seconds" in block:
        m = re.search(r"age=([\d.]+)<([\d.]+)", block)
        if m:
            left = max(0, int(float(m.group(2)) - float(m.group(1))))
            return f"мин. удержание ещё {left}с (из {int(float(m.group(2)))}с)"
    if "min_exit_move_bps" in block:
        m = re.search(r"favorable=([-\d.]+)<([\d.]+)", block)
        if m:
            return f"ход {float(m.group(1)):.0f} bps < мин. {float(m.group(2)):.0f} bps"
        m = re.search(r"move=([-\d.]+)<([\d.]+)", block)
        if m:
            return f"ход {float(m.group(1)):.0f} bps < мин. {float(m.group(2)):.0f} bps"
    if block == "no_price":
        return "нет цены для выхода"
    return block


def _position_levels(
    pos: Position,
    *,
    take_profit_pct: float | None,
    stop_loss_pct: float | None,
    broker_commission_rate: float | None,
    tax_pct: float | None,
) -> dict[str, float | None]:
    entry = float(pos.avg_entry_price or 0)
    is_long = str(getattr(pos, "side", "") or "LONG").upper() in ("LONG", "BUY")
    comm = float(broker_commission_rate or 0.0)
    out: dict[str, float | None] = {"entry": entry if entry > 0 else None, "be": None, "sl": None, "tp": None}
    if entry <= 0:
        return out
    out["be"] = calculate_break_even_price(entry, is_long=is_long, broker_commission_rate=comm)
    if stop_loss_pct and stop_loss_pct > 0:
        out["sl"] = calculate_stop_loss_price(
            entry, float(stop_loss_pct), is_long=is_long, broker_commission_rate=comm,
        )
    if take_profit_pct and take_profit_pct > 0:
        tax = (float(tax_pct) / 100.0) if tax_pct is not None else None
        out["tp"] = calculate_take_profit_price(
            entry,
            float(take_profit_pct),
            is_long=is_long,
            broker_commission_rate=comm,
            ndfl_rate=tax,
        )
    return out


def _in_position_scan_copy(
    pos: Position,
    *,
    price: float | None,
    flow: OrderFlowSnapshot | None,
    params: ScalperParams,
    take_profit_pct: float | None,
    stop_loss_pct: float | None,
    broker_commission_rate: float | None,
    tax_pct: float | None,
    guard: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Human scan text: what we wait for + current readings."""
    is_long = str(getattr(pos, "side", "") or "LONG").upper() in ("LONG", "BUY")
    thr = float(params.delta_threshold_pct)
    levels = _position_levels(
        pos,
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
        broker_commission_rate=broker_commission_rate,
        tax_pct=tax_pct,
    )
    wait: list[str] = []
    if levels["sl"] is not None:
        wait.append(f"SL {levels['sl']:.2f}")
    else:
        wait.append("SL")
    if levels["tp"] is not None:
        wait.append(f"TP {levels['tp']:.2f}")
    else:
        wait.append("TP")
    if is_long:
        wait.append(f"разворот delta ≤ −{thr:.0f}%")
    else:
        wait.append(f"разворот delta ≥ +{thr:.0f}%")

    now_bits: list[str] = []
    if price is not None and float(price) > 0:
        now_bits.append(f"цена {float(price):.2f}")
    if levels["entry"] is not None:
        now_bits.append(f"вход {levels['entry']:.2f}")
    if levels["be"] is not None:
        now_bits.append(f"безубыток {levels['be']:.2f}")
    if flow is None:
        now_bits.append("delta нет данных")
    else:
        need = f"≤ −{thr:.0f}%" if is_long else f"≥ +{thr:.0f}%"
        now_bits.append(f"delta {flow.delta_pct:+.1f}% (нужно {need})")

    extra: list[str] = []
    px = float(price or 0)
    be = levels["be"]
    if be is not None and px > 0:
        if is_long and px + 1e-9 < be:
            extra.append("стратегическую продажу не делаем — ниже безубытка")
        elif (not is_long) and px > be + 1e-9:
            extra.append("стратегическое закрытие short не делаем — выше безубытка")
        else:
            extra.append("стратегический выход разрешён не ниже безубытка")
    if guard:
        extra.append(_humanize_exit_guard(guard))

    if guard:
        head = f"Delta разворот есть, но выход отложен: {_humanize_exit_guard(guard)}."
    else:
        head = "В позиции — сигнала на продажу нет."
    msg = f"{head} Ждём: {' / '.join(wait)}. Сейчас: {', '.join(now_bits)}."
    if extra and not guard:
        msg = f"{msg} {extra[0].capitalize()}."
    elif extra and guard:
        rest = [x for x in extra if x != _humanize_exit_guard(guard)]
        if rest:
            msg = f"{msg} {rest[0].capitalize()}."

    metrics: dict[str, Any] = {
        "entryPrice": levels["entry"],
        "breakEven": levels["be"],
        "stopLoss": levels["sl"],
        "takeProfit": levels["tp"],
        "deltaThreshold": thr,
        "wait": " / ".join(wait),
    }
    if flow is not None:
        metrics.update(_flow_metrics(flow))
    if guard:
        metrics["blockReason"] = guard
    return msg, metrics


class ScalperPlugin(StrategyPlugin):
    archetype = "scalper"
    required_data = ["last_price", "websocket_trades", "orderbook_delta"]
    warmup_bars = 0
    entry_triggers = ["price_tick"]

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        params = ScalperParams.model_validate(ctx.config.params)
        signals: list[Signal] = []
        exits: list[Signal] = []
        entries: list[Signal] = []
        self._begin_scan()

        for ticker in ctx.universe:
            t = ticker.upper()
            if not self._in_universe(ctx, t):
                continue
            pos = has_open_position(ctx.open_positions, t)
            flow = (ctx.order_flow or {}).get(t)
            price = ctx.last_price.get(t)
            ts = self.ticker_state(t)

            if pos is not None:
                delta_reversal_long = (
                    flow is not None
                    and pos.side == "LONG"
                    and flow.delta_pct <= -params.delta_threshold_pct
                )
                delta_reversal_short = (
                    flow is not None
                    and pos.side == "SHORT"
                    and flow.delta_pct >= params.delta_threshold_pct
                )
                if delta_reversal_long or delta_reversal_short:
                    block = _exit_guard_reason(
                        pos,
                        price=price,
                        params=params,
                        now=ctx.now,
                        take_profit_pct=ctx.take_profit_pct,
                        broker_commission_rate=ctx.broker_commission_rate,
                        tax_pct=ctx.tax_pct,
                    )
                    if block:
                        message, metrics = _in_position_scan_copy(
                            pos,
                            price=price,
                            flow=flow,
                            params=params,
                            take_profit_pct=ctx.take_profit_pct,
                            stop_loss_pct=ctx.stop_loss_pct,
                            broker_commission_rate=ctx.broker_commission_rate,
                            tax_pct=ctx.tax_pct,
                            guard=block,
                        )
                        self._record_scan(
                            t,
                            code="EXIT_BLOCKED",
                            message=message,
                            price=price,
                            metrics=metrics,
                        )
                    else:
                        exits.append(make_exit_signal(ticker=t, reason="scalper_delta_reversal", price=price))
                        self._record_scan(
                            t, code="EXIT_SIGNAL",
                            message=(
                                f"Выход: delta {flow.delta_pct:.1f}% "
                                f"{'≤' if delta_reversal_long else '≥'} "
                                f"{'-' if delta_reversal_long else ''}{params.delta_threshold_pct}%"
                            ),
                            price=price,
                            metrics=_flow_metrics(flow, entryPrice=float(pos.avg_entry_price or 0)),
                        )
                else:
                    message, metrics = _in_position_scan_copy(
                        pos,
                        price=price,
                        flow=flow,
                        params=params,
                        take_profit_pct=ctx.take_profit_pct,
                        stop_loss_pct=ctx.stop_loss_pct,
                        broker_commission_rate=ctx.broker_commission_rate,
                        tax_pct=ctx.tax_pct,
                    )
                    self._record_scan(
                        t, code="IN_POSITION",
                        message=message,
                        price=price,
                        metrics=metrics,
                    )
                continue

            if ctx.triggered_by != "price_tick":
                self._record_scan(
                    t,
                    code="WRONG_TRIGGER",
                    message=f"Вход только на price_tick (сейчас {ctx.triggered_by})",
                    price=price,
                    metrics={"triggeredBy": ctx.triggered_by},
                )
                continue
            if flow is None:
                self._record_scan(
                    t,
                    code="NO_ORDER_FLOW",
                    message="Нет данных order-flow",
                    price=price,
                )
                continue
            if price is None:
                self._record_scan(t, code="NO_PRICE", message="Нет цены", price=price)
                continue

            if ctx.triggered_by == "price_tick":
                _update_price_history(ts, float(price), params.trend_lookback_ticks)

            sl_block = _sl_cooldown_block(ts, params, ctx.now)
            if sl_block:
                self._record_scan(
                    t,
                    code="SL_COOLDOWN",
                    message=f"Вход после SL заблокирован: {sl_block}",
                    price=price,
                    metrics={
                        **_flow_metrics(flow),
                        "stopLossCooldownSec": params.stop_loss_cooldown_sec,
                        "blockReason": sl_block,
                    },
                )
                continue

            last_trade_at = ts.get("lastTradeAt")
            if last_trade_at is not None:
                cooldown = timedelta(seconds=params.cooldown_sec)
                if ctx.now - last_trade_at < cooldown:
                    self._record_scan(
                        t,
                        code="COOLDOWN",
                        message=f"Cooldown {params.cooldown_sec}с не истёк",
                        price=price,
                        metrics=_flow_metrics(flow),
                    )
                    continue

            liquidity = flow.buy_volume + flow.sell_volume
            metrics = _flow_metrics(
                flow,
                liquidity=round(liquidity, 0),
                liquidityMin=MIN_ORDER_FLOW_LIQUIDITY,
                deltaThreshold=params.delta_threshold_pct,
            )
            if liquidity < MIN_ORDER_FLOW_LIQUIDITY:
                self._record_scan(
                    t,
                    code="LOW_LIQUIDITY",
                    message=f"Ликвидность {liquidity:.0f} < {MIN_ORDER_FLOW_LIQUIDITY:.0f}",
                    price=price,
                    metrics=metrics,
                )
                continue

            flow_block = _entry_flow_gate(flow, params)
            if flow_block:
                self._record_scan(
                    t,
                    code="THIN_ORDER_FLOW",
                    message=f"Вход заблокирован: {flow_block}",
                    price=price,
                    metrics={**metrics, "blockReason": flow_block},
                )
                continue

            if flow.delta_pct >= params.delta_threshold_pct:
                trend_block = _trend_block_long(ts, params)
                if trend_block:
                    self._record_scan(
                        t,
                        code="TREND_DOWN",
                        message=f"LONG заблокирован: {trend_block}",
                        price=price,
                        metrics={**metrics, "blockReason": trend_block},
                    )
                    continue
                entries.append(make_entry_signal(
                    ticker=t, side="BUY", reason="scalper_delta_cross", price=price,
                    strength=min(1.0, abs(flow.delta_pct) / max(params.delta_threshold_pct, 1)),
                ))
                ts["lastTradeAt"] = ctx.now
                ts["lastDelta"] = flow.delta_pct
                self._record_scan(
                    t, code="SIGNAL",
                    message=f"Сигнал BUY: delta {flow.delta_pct:.1f}% ≥ {params.delta_threshold_pct}%",
                    price=price, metrics=metrics,
                )
            elif ctx.allow_short and flow.delta_pct <= -params.delta_threshold_pct:
                entries.append(make_entry_signal(
                    ticker=t, side="SELL", reason="scalper_delta_cross", price=price,
                    strength=min(1.0, abs(flow.delta_pct) / max(params.delta_threshold_pct, 1)),
                ))
                ts["lastTradeAt"] = ctx.now
                ts["lastDelta"] = flow.delta_pct
                self._record_scan(
                    t, code="SIGNAL",
                    message=f"Сигнал SELL: delta {flow.delta_pct:.1f}% ≤ -{params.delta_threshold_pct}%",
                    price=price, metrics=metrics,
                )
            else:
                self._record_scan(
                    t,
                    code="DELTA_BELOW_THRESHOLD",
                    message=(
                        f"Delta {flow.delta_pct:.1f}% не достиг порога ±{params.delta_threshold_pct}%"
                    ),
                    price=price,
                    metrics=metrics,
                )

        signals.extend(exits)
        signals.extend(entries)
        return signals
