"""Conservative backtest credibility: intrabar SL/TP, NDFL, liquidity, cost stress."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.modules.trading_core.contracts import Candle, OrderIntent
from app.modules.trading_core.costs import (
    TradingCosts,
    calculate_stop_loss_price,
    calculate_take_profit_price,
)
from app.modules.trading_core.risk.manager import should_skip_take_profit
from app.modules.trading_core.symbols import normalize_figi

LIQUIDITY_PARTICIPATION = 0.10


def cap_fill_quantity(
    qty: int,
    bar_volume: float | None,
    *,
    participation: float = LIQUIDITY_PARTICIPATION,
) -> tuple[int, bool]:
    """Cap a fill by a fraction of the bar's traded volume.

    Unknown / non-positive volume is left uncapped (we do not invent liquidity).
    """
    q = int(qty or 0)
    if q <= 0:
        return 0, False
    try:
        vol = float(bar_volume) if bar_volume is not None else 0.0
    except (TypeError, ValueError):
        return q, False
    if vol <= 0 or participation <= 0:
        return q, False
    cap = max(1, int(vol * float(participation)))
    if q <= cap:
        return q, False
    return cap, True


def apply_liquidity_cap(
    intent: OrderIntent,
    bar_volume: float | None,
    *,
    participation: float = LIQUIDITY_PARTICIPATION,
) -> tuple[OrderIntent, int, bool]:
    """Return (possibly smaller intent, remainder qty, capped?)."""
    qty = int(intent.quantity or 0)
    filled, capped = cap_fill_quantity(qty, bar_volume, participation=participation)
    if not capped:
        return intent, 0, False
    meta = dict(getattr(intent, "meta", None) or {})
    meta["liquidity_capped"] = True
    meta["requested_qty"] = qty
    meta["bar_volume"] = bar_volume
    return replace(intent, quantity=float(filled), meta=meta), qty - filled, True


def _bar_for(bars: dict[str, Any] | None, figi: str | None, figi_key: str | None) -> Candle | None:
    if not bars:
        return None
    for key in (figi, figi_key, str(figi or "").upper(), str(figi_key or "").upper()):
        if not key:
            continue
        raw = bars.get(key)
        if raw is None:
            continue
        if isinstance(raw, Candle):
            return raw
        break
    return None


def intrabar_protective_hit(
    *,
    is_long: bool,
    stop_loss: float,
    take_profit: float,
    high: float,
    low: float,
) -> tuple[str, float] | None:
    """Conservative same-bar rule: if both SL and TP are touched, SL wins."""
    hi = float(high or 0)
    lo = float(low or 0)
    if hi <= 0 or lo <= 0:
        return None
    if is_long:
        sl_hit = stop_loss > 0 and lo <= stop_loss
        tp_hit = take_profit > 0 and hi >= take_profit
        if sl_hit:
            return "stop_loss", float(stop_loss)
        if tp_hit:
            return "take_profit", float(take_profit)
        return None
    sl_hit = stop_loss > 0 and hi >= stop_loss
    tp_hit = take_profit > 0 and lo <= take_profit
    if sl_hit:
        return "stop_loss", float(stop_loss)
    if tp_hit:
        return "take_profit", float(take_profit)
    return None


def plan_intrabar_sl_tp_intents(
    open_positions: list[dict[str, Any]],
    prices: dict[str, float],
    bars: dict[str, Any],
    risk_params: dict[str, Any],
    *,
    cost_kw: dict[str, float] | None = None,
    now: Any = None,
) -> list[OrderIntent]:
    """MARKET SL/TP fills at the stop/target when the bar's high/low proves a touch."""
    intents: list[OrderIntent] = []
    stop_loss_percent = risk_params.get("stop_loss_percent", 2)
    take_profit_percent = risk_params.get("take_profit_percent", 3)
    kw = dict(cost_kw or {})

    for position in open_positions or []:
        figi = position.get("figi") or position.get("ticker") or position.get("secid")
        figi_key = normalize_figi(figi)
        entry_price = float(position.get("entry_price") or 0)
        quantity = float(position.get("quantity") or 0)
        is_long = str(position.get("side", "")).lower() in {"buy", "long"}
        if entry_price <= 0 or quantity <= 0:
            continue
        bar = _bar_for(bars, str(figi) if figi is not None else None, figi_key)
        if bar is None:
            continue
        stop_loss = calculate_stop_loss_price(
            entry_price,
            stop_loss_percent,
            is_long=is_long,
            broker_commission_rate=kw.get("broker_commission_rate"),
        )
        take_profit = calculate_take_profit_price(
            entry_price, take_profit_percent, is_long=is_long, **kw
        )
        hit = intrabar_protective_hit(
            is_long=is_long,
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            high=float(bar.high),
            low=float(bar.low),
        )
        if hit is None:
            continue
        reason, exit_px = hit
        if reason == "take_profit":
            block = should_skip_take_profit(
                position,
                current_price=float(prices.get(figi_key or str(figi or ""), bar.close) or bar.close),
                risk_params=risk_params,
                now=now,
            )
            if block:
                continue
        side = "BUY" if not is_long else "SELL"
        costs = TradingCosts(entry_price, float(quantity), is_buy=is_long, **kw)
        profit_calc = costs.calculate_actual_profit(exit_px)
        trade_id = position.get("id")
        intents.append(
            OrderIntent(
                kind="exit_sl_tp",
                figi=figi_key or str(figi or ""),
                side=side,  # type: ignore[arg-type]
                quantity=quantity,
                price=float(exit_px),
                reduce_only=True,
                reason=reason,
                order_type="MARKET",
                trade_id=int(trade_id) if trade_id is not None else None,
                estimated_profit=float(profit_calc.get("net_profit") or 0),
                meta={
                    "position_side": position.get("side"),
                    "entry_price": entry_price,
                    "mark_price": float(bar.close),
                    "take_profit": float(take_profit),
                    "stop_loss": float(stop_loss),
                    "intrabar": True,
                },
            )
        )
    return intents


def _trade_notional(trade: dict[str, Any]) -> float:
    try:
        return abs(float(trade.get("price") or 0) * float(trade.get("quantity") or 0))
    except (TypeError, ValueError):
        return 0.0


def _closed_pnls(trades: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for t in trades:
        pnl = t.get("pnl_net")
        if pnl is None:
            continue
        try:
            out.append(float(pnl))
        except (TypeError, ValueError):
            continue
    return out


def build_cost_stress(
    *,
    trades: list[dict[str, Any]],
    initial_capital: float,
    final_equity: float,
    slippage_pct: float,
) -> dict[str, Any]:
    """Post-hoc overlay: extra 50% commission and a second slippage pass.

    This is not a re-simulation — it answers «does the edge survive worse costs?»
    """
    commission_total = 0.0
    notional = 0.0
    for t in trades:
        try:
            commission_total += float(t.get("commission") or 0)
        except (TypeError, ValueError):
            pass
        notional += _trade_notional(t)

    extra_comm = commission_total * 0.5
    extra_slip = notional * (max(float(slippage_pct or 0), 0.0) / 100.0)
    initial = float(initial_capital or 0)
    base_eq = float(final_equity or 0)

    def _case(extra: float) -> dict[str, float]:
        eq = round(base_eq - extra, 2)
        ret = 0.0
        if initial > 0:
            ret = (eq - initial) / initial * 100.0
        return {
            "final_equity": eq,
            "total_return_percent": round(ret, 4),
            "extra_cost": round(extra, 6),
        }

    return {
        "commission_plus_50pct": _case(extra_comm),
        "slippage_x2": _case(extra_slip),
        "combined": _case(extra_comm + extra_slip),
    }


def build_exposure_turnover(
    *,
    snapshots: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    initial_capital: float,
) -> dict[str, float | None]:
    exposures: list[float] = []
    for snap in snapshots or []:
        try:
            equity = float(snap.get("equity") or 0)
            cash = float(snap.get("cash") or 0)
        except (TypeError, ValueError):
            continue
        if equity <= 0:
            continue
        exposures.append(abs(equity - cash) / equity * 100.0)
    avg_exposure = round(sum(exposures) / len(exposures), 4) if exposures else None
    turnover = None
    initial = float(initial_capital or 0)
    if initial > 0:
        turnover = round(sum(_trade_notional(t) for t in trades) / initial, 6)
    pnls = _closed_pnls(trades)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    return {
        "avg_exposure_pct": avg_exposure,
        "turnover": turnover,
        "avg_win": round(sum(wins) / len(wins), 4) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 4) if losses else None,
    }


def build_credibility_report(
    *,
    trades: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    initial_capital: float,
    final_equity: float,
    slippage_pct: float,
    ndfl: bool,
    tax_total: float = 0.0,
    liquidity_participation: float = LIQUIDITY_PARTICIPATION,
) -> dict[str, Any]:
    exposure = build_exposure_turnover(
        snapshots=snapshots,
        trades=trades,
        initial_capital=initial_capital,
    )
    return {
        "intrabar_sl_tp": True,
        "sl_before_tp": True,
        "ndfl": bool(ndfl),
        "tax_total": round(float(tax_total or 0), 6),
        "liquidity_participation": float(liquidity_participation),
        "cost_stress": build_cost_stress(
            trades=trades,
            initial_capital=initial_capital,
            final_equity=final_equity,
            slippage_pct=slippage_pct,
        ),
        **exposure,
        "assumptions": (
            "SL/TP по high/low бара (стоп раньше тейка); "
            "НДФЛ с прибыльных закрытий; "
            f"лимит участия {int(liquidity_participation * 100)}% объёма бара; "
            "стресс издержек — аналитический overlay, не повторный прогон."
        ),
    }
