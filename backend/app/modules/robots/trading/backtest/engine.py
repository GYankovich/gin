"""
Бэктестинг стратегий на исторических свечах (без реальных сделок).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.modules.robots.trading.costs import (
    TradingCosts,
    calculate_position_size,
    resolve_robot_cost_rates,
)
from app.modules.robots.trading.strategies import get_strategy_class
from app.modules.tinvest.methods.instruments import InstrumentsClient


def _close_price(candle: Dict[str, Any]) -> float:
    cl = candle.get("close") or {}
    return float(int(cl.get("units", 0) or 0)) + float(int(cl.get("nano", 0) or 0)) / 1e9


def _candle_time_iso(candle: Dict[str, Any]) -> str:
    t = candle.get("time")
    if isinstance(t, str):
        return t
    if isinstance(t, dict):
        return str(t.get("seconds", ""))
    return ""


@dataclass
class _Position:
    figi: str
    quantity: int
    entry_price: float
    side: str = "buy"


@dataclass
class BacktestResult:
    initial_capital: float
    final_equity: float
    total_return_percent: float
    max_drawdown_percent: Optional[float]
    trades: List[Dict[str, Any]] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)


def _merge_cost_rates(
        risk: Dict[str, Any],
        cost_override: Optional[Dict[str, Any]],
        robot_config_for_defaults: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    base: Dict[str, Any] = {}
    if robot_config_for_defaults:
        base.update(robot_config_for_defaults.get("costs") or {})
    if cost_override:
        for k, v in cost_override.items():
            if v is not None:
                base[k] = v
    br, tx = resolve_robot_cost_rates({"costs": base})
    r = dict(risk)
    r["broker_commission"] = br
    r["ndfl"] = tx
    return r, {"broker_commission_rate": br, "ndfl_rate": tx}


async def run_backtest_simulation(
        *,
        candles_by_figi: Dict[str, List[Dict[str, Any]]],
        strategy_name: str,
        strategy_params: Dict[str, Any],
        risk_params: Dict[str, Any],
        initial_capital: float = 1_000_000.0,
        cost_override: Optional[Dict[str, Any]] = None,
        robot_config_for_cost_defaults: Optional[Dict[str, Any]] = None,
) -> BacktestResult:
    """
    Прогон стратегии по уже загруженным свечам (одна long-позиция на FIGI, BUY/SELL).
    """
    figis: List[str] = list(candles_by_figi.keys())
    if not figis:
        raise ValueError("Нет свечей")

    sp = dict(strategy_params)
    sp["figis"] = figis

    risk, cost_kw = _merge_cost_rates(risk_params, cost_override, robot_config_for_cost_defaults)

    lengths = [len(candles_by_figi[f]) for f in figis]
    if not lengths or min(lengths) < 3:
        raise ValueError("Недостаточно свечей за выбранный период")

    min_len = min(lengths)
    for f in figis:
        candles_by_figi[f] = candles_by_figi[f][:min_len]

    strategy_class = get_strategy_class(strategy_name)
    strategy = strategy_class(None, sp)

    try:
        warmup = await strategy.get_required_candles_count()
    except Exception:
        warmup = 50
    warmup = max(2, min(warmup, min_len - 1))

    cash = float(initial_capital)
    positions: Dict[str, _Position] = {}
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []

    peak_equity = float(initial_capital)
    max_dd_pct: Optional[float] = None

    for i in range(warmup, min_len):
        snap = {f: candles_by_figi[f][: i + 1] for f in figis}
        raw_signals = await strategy.generate_signals(snap)

        ref_candle = candles_by_figi[figis[0]][i]
        bar_time = _candle_time_iso(ref_candle)

        portfolio_value = cash
        for figi, pos in positions.items():
            px = _close_price(candles_by_figi[figi][i])
            portfolio_value += pos.quantity * px
        equity_pre = portfolio_value

        open_figis = set(positions.keys())

        for figi in figis:
            sig = raw_signals.get(figi)
            if not sig or str(sig).upper() not in ("BUY", "SELL"):
                continue
            price = _close_price(candles_by_figi[figi][i])
            if price <= 0:
                continue

            side = str(sig).upper()

            if side == "BUY" and figi not in open_figis:
                max_pct = float(risk.get("max_position_percent", 10) or 10)
                max_rub = risk.get("max_position_rub")
                max_rub_f = float(max_rub) if max_rub is not None else None
                qty = calculate_position_size(
                    portfolio_value=max(equity_pre, 1.0),
                    current_price=price,
                    max_position_percent=max_pct,
                    max_position_rub=max_rub_f,
                    free_funds=cash,
                )
                if qty <= 0:
                    continue
                invest = price * qty
                tc_open = TradingCosts(price, qty, is_buy=True, **cost_kw)
                comm = tc_open.calculate_commission()
                if cash < invest + comm:
                    continue
                cash -= invest + comm
                positions[figi] = _Position(figi=figi, quantity=qty, entry_price=price, side="buy")
                open_figis.add(figi)
                trades.append({
                    "id": len(trades) + 1,
                    "figi": figi,
                    "side": "buy",
                    "bar_time": bar_time,
                    "price": round(price, 6),
                    "quantity": qty,
                    "commission": round(comm, 4),
                    "pnl_net": None,
                })

            elif side == "SELL" and figi in positions:
                pos = positions.pop(figi)
                tc = TradingCosts(pos.entry_price, pos.quantity, is_buy=True, **cost_kw)
                act = tc.calculate_actual_profit(price)
                cash += price * pos.quantity - act["commission_sell"] - act["tax"]
                trades.append({
                    "id": len(trades) + 1,
                    "figi": figi,
                    "side": "sell",
                    "bar_time": bar_time,
                    "price": round(price, 6),
                    "quantity": pos.quantity,
                    "commission": round(act["commission_buy"] + act["commission_sell"], 4),
                    "pnl_net": round(act["net_profit"], 4),
                })
                open_figis.discard(figi)

        mark_equity = cash
        for figi, pos in positions.items():
            px = _close_price(candles_by_figi[figi][i])
            mark_equity += pos.quantity * px

        equity_curve.append({"time": bar_time, "equity": round(mark_equity, 2)})

        if mark_equity > peak_equity:
            peak_equity = mark_equity
        if peak_equity > 0:
            dd = (peak_equity - mark_equity) / peak_equity * 100.0
            if max_dd_pct is None or dd > max_dd_pct:
                max_dd_pct = dd

    final_equity = equity_curve[-1]["equity"] if equity_curve else float(initial_capital)
    ret_pct = (final_equity / float(initial_capital) - 1.0) * 100.0 if initial_capital else 0.0

    return BacktestResult(
        initial_capital=float(initial_capital),
        final_equity=float(final_equity),
        total_return_percent=round(ret_pct, 4),
        max_drawdown_percent=round(max_dd_pct, 4) if max_dd_pct is not None else None,
        trades=trades,
        equity_curve=equity_curve,
    )


async def run_robot_backtest(
        *,
        token: str,
        robot_config: Dict[str, Any],
        from_date: datetime,
        to_date: datetime,
        initial_capital: float = 1_000_000.0,
) -> BacktestResult:
    """Загружает свечи через API по конфигу робота и запускает симуляцию."""
    figis: List[str] = list(robot_config.get("allowed_figis") or robot_config.get("strategy_params", {}).get("figis") or [])
    if not figis:
        raise ValueError("В конфиге робота нет allowed_figis")

    strategy_name = robot_config.get("strategy") or "grain_seed"
    strategy_params = dict(robot_config.get("strategy_params") or {})
    strategy_params["figis"] = figis
    interval = strategy_params.get("interval", "CANDLE_INTERVAL_DAY")
    risk = dict(robot_config.get("risk") or {})

    client = InstrumentsClient(token)
    candles_by_figi: Dict[str, List[Dict[str, Any]]] = {}
    for figi in figis:
        raw = await client.get_candles(figi, from_date, to_date, interval)
        candles_by_figi[figi] = list(raw or [])

    return await run_backtest_simulation(
        candles_by_figi=candles_by_figi,
        strategy_name=strategy_name,
        strategy_params=strategy_params,
        risk_params=risk,
        initial_capital=initial_capital,
        robot_config_for_cost_defaults=robot_config,
    )
