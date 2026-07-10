"""
Бэктестинг стратегий на исторических свечах (без реальных сделок).

DEPRECATED для prod (BRD-ARCH-04 этап 3): используйте `TradingOrchestrator.run_backtest_replay`.
Модуль оставлен для unit-тестов grain_seed и постепенного вывода монолита.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime, time, timezone
import asyncio
import bisect
import time as time_mod
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from app.modules.robots.trading.grain_seed_orchestrator import (
    compute_effective_free_funds,
    parse_force_close_time,
)

from app.modules.robots.trading.costs import (
    TradingCosts,
    resolve_robot_cost_rates,
)
from app.modules.robots.trading.backtest.types import (
    BacktestResult,
    _bar_in_trading_session,
    _candle_time_iso,
    _iso_to_msk_time_of_day,
    _session_time_from_risk,
    candle_time_iso,
)
from .broker_emulator import BrokerEmulator
from .virtual_portfolio import VirtualPortfolio
from .sim_executor import SimExecutor
from app.modules.robots.trading.strategies import get_strategy_class
from app.modules.tinvest.methods.instruments import InstrumentsClient


def _close_price(candle: Dict[str, Any]) -> float:
    cl = candle.get("close") or {}
    return float(int(cl.get("units", 0) or 0)) + float(int(cl.get("nano", 0) or 0)) / 1e9


def _open_price(candle: Dict[str, Any]) -> float:
    op = candle.get("open") or {}
    return float(int(op.get("units", 0) or 0)) + float(int(op.get("nano", 0) or 0)) / 1e9


def _high_price(candle: Dict[str, Any]) -> float:
    hp = candle.get("high") or {}
    return float(int(hp.get("units", 0) or 0)) + float(int(hp.get("nano", 0) or 0)) / 1e9


def _low_price(candle: Dict[str, Any]) -> float:
    lp = candle.get("low") or {}
    return float(int(lp.get("units", 0) or 0)) + float(int(lp.get("nano", 0) or 0)) / 1e9


@dataclass
class _Position:
    figi: str
    quantity: int
    entry_price: float
    side: str = "buy"
    peak_price: float = 0.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


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


def _enrich_risk_from_strategy_params(risk: Dict[str, Any], sp: Dict[str, Any]) -> Dict[str, Any]:
    """Поля риска, которые в UI лежат в strategy_params, но нужны движку (ТЗ / GrainSeed)."""
    out = dict(risk)
    if out.get("risk_per_trade_pct") is None and sp.get("risk_per_trade_pct") is not None:
        out["risk_per_trade_pct"] = float(sp["risk_per_trade_pct"])
    return out


def _series_prefix_tail_for_bar(
        *,
        series: List[Dict[str, Any]],
        times: List[str],
        bar_time: str,
        warmup: int,
        tail_keep: int,
) -> Optional[List[Dict[str, Any]]]:
    """Префикс ряда до bar_time (включительно), с обрезкой слева для O(1) по длине ряда на бар.

    Индикаторы стратегии опираются на хвост; длина tail_keep >= warmup + запас под MA/BB/ATR.
    """
    if not series or not times or len(series) != len(times):
        return None
    hi = bisect.bisect_right(times, bar_time)
    if hi <= 0:
        return None
    seq_full = series[:hi]
    if len(seq_full) < warmup:
        return None
    if len(seq_full) > tail_keep:
        return seq_full[-tail_keep:]
    return seq_full


def _close_at_or_before(series: List[Dict[str, Any]], times: List[str], bar_time: str) -> float:
    if not series or not times or len(series) != len(times):
        return 0.0
    hi = bisect.bisect_right(times, bar_time)
    if hi <= 0:
        return 0.0
    return _close_price(series[hi - 1])


def _risk_budget_max_quantity(
        *,
        portfolio_value: float,
        entry_price: float,
        risk_per_trade_pct: float,
        stop_loss_pct: float,
) -> Optional[int]:
    if portfolio_value <= 0 or entry_price <= 0 or risk_per_trade_pct <= 0 or stop_loss_pct <= 0:
        return None
    max_loss_rub = portfolio_value * (risk_per_trade_pct / 100.0)
    loss_per_unit = entry_price * (stop_loss_pct / 100.0)
    if loss_per_unit <= 0:
        return None
    q = int(max_loss_rub // loss_per_unit)
    return q if q > 0 else None


def _run_generate_signals_blocking(strategy: Any, snap: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Optional[str]]:
    """Pandas/стратегия в worker-thread — не блокирует event loop FastAPI."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(strategy.generate_signals(snap))
    finally:
        try:
            loop.close()
        except Exception:
            pass


#///EPIC Backtesting.ITEM SimulationEngine.TOPIC Intraday Loop [1]
#/// Ядро симуляции: строит внутридневной цикл по bar_time, запрашивает сигналы стратегии,
#/// выполняет виртуальные сделки через broker/sim_executor, обновляет equity/drawdown
#/// и формирует артефакты (signals, trades, equity_curve, daily_positions).
async def run_backtest_simulation(
        *,
        candles_by_figi: Dict[str, List[Dict[str, Any]]],
        strategy_name: str,
        strategy_params: Dict[str, Any],
        risk_params: Dict[str, Any],
        initial_capital: float = 1_000_000.0,
        cost_override: Optional[Dict[str, Any]] = None,
        robot_config_for_cost_defaults: Optional[Dict[str, Any]] = None,
        allowed_figis_by_date: Optional[Dict[str, List[str]]] = None,
        execution_model: str = "NEXT_BAR_OPEN",
        slippage_pct: float = 0.0,
        cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
        cancel_check_sync: Optional[Callable[[], bool]] = None,
        progress_callback_sync: Optional[Callable[[int, int], None]] = None,
) -> BacktestResult:
    """
    Прогон стратегии по уже загруженным свечам (одна long-позиция на FIGI, BUY/SELL).
    """
    warnings.warn(
        "run_backtest_simulation is deprecated; use TradingOrchestrator.run_backtest_replay",
        DeprecationWarning,
        stacklevel=2,
    )
    figis: List[str] = list(candles_by_figi.keys())
    if not figis:
        raise ValueError("Нет свечей")

    sp = dict(strategy_params)
    sp["figis"] = figis

    risk, cost_kw = _merge_cost_rates(risk_params, cost_override, robot_config_for_cost_defaults)
    risk = _enrich_risk_from_strategy_params(risk, sp)

    lengths = [len(candles_by_figi[f]) for f in figis]
    if not lengths or max(lengths) < 3:
        raise ValueError("Недостаточно свечей за выбранный период")

    strategy_class = get_strategy_class(strategy_name)
    strategy = strategy_class(None, sp)

    try:
        warmup = int(await strategy.get_required_candles_count())
    except Exception:
        warmup = 50
    warmup = max(2, warmup)

    cash = float(initial_capital)
    positions: Dict[str, _Position] = {}
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []
    signals: List[Dict[str, Any]] = []
    daily_positions: List[Dict[str, Any]] = []

    peak_equity = float(initial_capital)
    max_dd_pct: Optional[float] = None
    portfolio = VirtualPortfolio(initial_capital=float(initial_capital))
    broker = BrokerEmulator(execution_model=execution_model, slippage_pct=slippage_pct)
    executor = SimExecutor()
    allowed_map = {
        str(k): {str(x).upper() for x in (v or []) if x}
        for k, v in (allowed_figis_by_date or {}).items()
    }

    candles_by_day: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    full_series_by_figi: Dict[str, List[Dict[str, Any]]] = {}
    idx_by_figi_time: Dict[str, Dict[str, int]] = {}
    for f in figis:
        series_full = sorted(list(candles_by_figi.get(f, [])), key=lambda c: _candle_time_iso(c))
        full_series_by_figi[f] = series_full
        idx_by_figi_time[f] = {_candle_time_iso(c): i for i, c in enumerate(series_full) if _candle_time_iso(c)}
        for c in series_full:
            t = _candle_time_iso(c)
            if not t or len(t) < 10:
                continue
            day = t[:10]
            candles_by_day.setdefault(day, {}).setdefault(f, []).append(c)

    times_by_figi: Dict[str, List[str]] = {
        f: [_candle_time_iso(c) for c in full_series_by_figi[f]]
        for f in figis
    }
    tail_keep = max(warmup + 200, int(sp.get("sim_indicator_tail", 960) or 960))

    consecutive_loss_days = 0
    cooling_no_new_entries = False
    last_cancel_poll_mono = 0.0
    equity_sample_stride = max(1, int(sp.get("equity_curve_sample_stride", 6) or 6))

    session_start_pre = _session_time_from_risk(risk.get("trading_hours_start"), "10:00")
    session_end_pre = _session_time_from_risk(risk.get("trading_hours_end"), "18:45")
    bars_total = 0
    for _day in sorted(candles_by_day.keys()):
        _dm = candles_by_day.get(_day) or {}
        _figs = sorted(_dm.keys())
        if not _figs:
            continue
        _times = sorted(
            {(_candle_time_iso(c) or "") for _ff in _figs for c in _dm.get(_ff, []) if _candle_time_iso(c)}
        )
        _times = [bt for bt in _times if _bar_in_trading_session(bt, session_start_pre, session_end_pre)]
        bars_total += len(_times)
    bars_processed = 0
    if progress_callback_sync is not None and bars_total > 0:
        try:
            progress_callback_sync(0, bars_total)
        except Exception:
            pass

    for day in sorted(candles_by_day.keys()):
        if cancel_check_sync is not None and cancel_check_sync():
            final_equity = equity_curve[-1]["equity"] if equity_curve else float(initial_capital)
            ret_pct = (final_equity / float(initial_capital) - 1.0) * 100.0 if initial_capital else 0.0
            return BacktestResult(
                initial_capital=float(initial_capital),
                final_equity=float(final_equity),
                total_return_percent=round(ret_pct, 4),
                max_drawdown_percent=round(max_dd_pct, 4) if max_dd_pct is not None else None,
                trades=trades,
                equity_curve=equity_curve,
                signals=signals,
                daily_positions=daily_positions,
                cancelled=True,
            )
        if cancel_check is not None:
            try:
                if await cancel_check():
                    final_equity = equity_curve[-1]["equity"] if equity_curve else float(initial_capital)
                    ret_pct = (final_equity / float(initial_capital) - 1.0) * 100.0 if initial_capital else 0.0
                    return BacktestResult(
                        initial_capital=float(initial_capital),
                        final_equity=float(final_equity),
                        total_return_percent=round(ret_pct, 4),
                        max_drawdown_percent=round(max_dd_pct, 4) if max_dd_pct is not None else None,
                        trades=trades,
                        equity_curve=equity_curve,
                        signals=signals,
                        daily_positions=daily_positions,
                        cancelled=True,
                    )
            except Exception:
                pass
        day_map = candles_by_day.get(day) or {}
        day_figis = sorted(day_map.keys())
        if not day_figis:
            continue
        day_times = sorted({(_candle_time_iso(c) or "") for ff in day_figis for c in day_map.get(ff, []) if _candle_time_iso(c)})
        if not day_times:
            continue
        session_start = _session_time_from_risk(risk.get("trading_hours_start"), "10:00")
        session_end = _session_time_from_risk(risk.get("trading_hours_end"), "18:45")
        day_times = [bt for bt in day_times if _bar_in_trading_session(bt, session_start, session_end)]
        if not day_times:
            continue
        allowed_today = allowed_map.get(day) if day in allowed_map else None

        reserve_pct = float(sp.get("free_funds_reserve_pct", 50.0) or 0.0)
        streak_limit = int(sp.get("day_loss_streak_limit", 3) or 3)
        broker_type = str((config or {}).get("broker_type") or "tinvest").strip().lower()
        flatten_default = False if broker_type == "bybit" else True
        force_flatten = (
            bool(sp.get("force_market_flatten", flatten_default))
            and bool(str(sp.get("force_close_time_msk") or "").strip())
        )
        risk_pt = float(risk.get("risk_per_trade_pct") or 0.0)
        stop_pct = float(risk.get("stop_loss_percent") or 0.0)
        tp_pct = float(risk.get("take_profit_percent") or 0.0)
        max_daily_loss = float(risk.get("max_daily_loss") or 0.0)
        pause_entries_today = False
        if cooling_no_new_entries:
            cooling_no_new_entries = False
            pause_entries_today = True
        day_start_equity: Optional[float] = None
        day_block_new_buys = False

        for i_bt, bar_time in enumerate(day_times):
            if cancel_check_sync is not None and cancel_check_sync():
                final_equity = equity_curve[-1]["equity"] if equity_curve else float(initial_capital)
                ret_pct = (final_equity / float(initial_capital) - 1.0) * 100.0 if initial_capital else 0.0
                return BacktestResult(
                    initial_capital=float(initial_capital),
                    final_equity=float(final_equity),
                    total_return_percent=round(ret_pct, 4),
                    max_drawdown_percent=round(max_dd_pct, 4) if max_dd_pct is not None else None,
                    trades=trades,
                    equity_curve=equity_curve,
                    signals=signals,
                    daily_positions=daily_positions,
                    cancelled=True,
                )
            if cancel_check is not None:
                try:
                    if await cancel_check():
                        final_equity = equity_curve[-1]["equity"] if equity_curve else float(initial_capital)
                        ret_pct = (final_equity / float(initial_capital) - 1.0) * 100.0 if initial_capital else 0.0
                        return BacktestResult(
                            initial_capital=float(initial_capital),
                            final_equity=float(final_equity),
                            total_return_percent=round(ret_pct, 4),
                            max_drawdown_percent=round(max_dd_pct, 4) if max_dd_pct is not None else None,
                            trades=trades,
                            equity_curve=equity_curve,
                            signals=signals,
                            daily_positions=daily_positions,
                            cancelled=True,
                        )
                except Exception:
                    pass
            snap: Dict[str, List[Dict[str, Any]]] = {}
            for ff in day_figis:
                seq = _series_prefix_tail_for_bar(
                    series=full_series_by_figi.get(ff, []),
                    times=times_by_figi.get(ff, []),
                    bar_time=bar_time,
                    warmup=warmup,
                    tail_keep=tail_keep,
                )
                if seq is not None:
                    snap[ff] = seq
            if not snap:
                continue

            portfolio_value = cash
            for figi, pos in positions.items():
                pxv = _close_at_or_before(
                    full_series_by_figi.get(figi, []),
                    times_by_figi.get(figi, []),
                    bar_time,
                )
                if pxv > 0:
                    portfolio_value += pos.quantity * pxv
            equity_pre = portfolio_value
            if day_start_equity is None:
                day_start_equity = equity_pre
            if max_daily_loss > 0 and day_start_equity is not None:
                if (day_start_equity - equity_pre) >= max_daily_loss:
                    day_block_new_buys = True

            if stop_pct > 0 and tp_pct > 0:
                for figi_ps in list(positions.keys()):
                    pos_sl = positions.get(figi_ps)
                    if not pos_sl:
                        continue
                    s_sl = full_series_by_figi.get(figi_ps, [])
                    t_sl = times_by_figi.get(figi_ps, [])
                    hi_sl = bisect.bisect_right(t_sl, bar_time)
                    if hi_sl <= 0 or _candle_time_iso(s_sl[hi_sl - 1]) != bar_time:
                        continue
                    cur_sl = s_sl[hi_sl - 1]
                    lo = _low_price(cur_sl)
                    hi = _high_price(cur_sl)
                    ep = pos_sl.entry_price
                    sl_px = ep * (1.0 - stop_pct / 100.0)
                    tp_px = ep * (1.0 + tp_pct / 100.0)
                    exit_px: Optional[float] = None
                    exit_reason = ""
                    if lo <= sl_px:
                        exit_px = sl_px
                        exit_reason = "stop_loss"
                    elif hi >= tp_px:
                        exit_px = tp_px
                        exit_reason = "take_profit"
                    if exit_px is None or exit_px <= 0:
                        continue
                    positions.pop(figi_ps, None)
                    tco = TradingCosts(pos_sl.entry_price, pos_sl.quantity, is_buy=False, **cost_kw)
                    acto = tco.calculate_actual_profit(exit_px)
                    cash += exit_px * pos_sl.quantity - acto["commission_sell"] - acto["tax"]
                    trades.append({
                        "id": len(trades) + 1,
                        "figi": figi_ps,
                        "side": "sell",
                        "bar_time": bar_time,
                        "price": round(exit_px, 6),
                        "quantity": pos_sl.quantity,
                        "commission": round(acto["commission_buy"] + acto["commission_sell"], 4),
                        "pnl_net": round(acto["net_profit"], 4),
                    })
                    signals.append({
                        "id": len(signals) + 1,
                        "figi": figi_ps,
                        "signal_type": "sell",
                        "bar_time": bar_time,
                        "price": round(exit_px, 6),
                        "was_executed": 1,
                        "reason": exit_reason,
                    })

            trailing_stop_pct = _safe_float(sp.get("trailing_stop_percent", 0.0), 0.0)
            if trailing_stop_pct > 0:
                for figi in list(positions.keys()):
                    pos = positions.get(figi)
                    if not pos:
                        continue
                    px = _close_at_or_before(
                        full_series_by_figi.get(figi, []),
                        times_by_figi.get(figi, []),
                        bar_time,
                    )
                    if px <= 0:
                        continue
                    if pos.peak_price <= 0:
                        pos.peak_price = max(pos.entry_price, px)
                    pos.peak_price = max(pos.peak_price, px)
                    stop_px = pos.peak_price * (1.0 - trailing_stop_pct / 100.0)
                    if px <= stop_px:
                        tc = TradingCosts(pos.entry_price, pos.quantity, is_buy=False, **cost_kw)
                        act = tc.calculate_actual_profit(px)
                        cash += px * pos.quantity - act["commission_sell"] - act["tax"]
                        trades.append({
                            "id": len(trades) + 1,
                            "figi": figi,
                            "side": "sell",
                            "bar_time": bar_time,
                            "price": round(px, 6),
                            "quantity": pos.quantity,
                            "commission": round(act["commission_buy"] + act["commission_sell"], 4),
                            "pnl_net": round(act["net_profit"], 4),
                        })
                        signals.append({
                            "id": len(signals) + 1,
                            "figi": figi,
                            "signal_type": "sell",
                            "bar_time": bar_time,
                            "price": round(px, 6),
                            "was_executed": 1,
                            "reason": "trailing_stop_executed",
                        })
                        positions.pop(figi, None)

            if cancel_check_sync is not None and cancel_check_sync():
                raw_signals = {}
            else:
                raw_signals = await asyncio.to_thread(_run_generate_signals_blocking, strategy, snap)
            open_figis = set(positions.keys())

            for figi in day_figis:
                seq = snap.get(figi)
                if not seq:
                    continue
                idx_local = len(seq) - 1
                sig = raw_signals.get(figi)
                if not sig or str(sig).upper() not in ("BUY", "SELL"):
                    continue

                side = str(sig).upper()
                cur_candle = seq[idx_local]
                cur_time = _candle_time_iso(cur_candle)
                cur_idx = idx_by_figi_time.get(figi, {}).get(cur_time)
                nxt_candle = (
                    full_series_by_figi.get(figi, [])[cur_idx + 1]
                    if cur_idx is not None and (cur_idx + 1) < len(full_series_by_figi.get(figi, []))
                    else None
                )
                synthetic_series = [cur_candle] + ([nxt_candle] if nxt_candle is not None else [])
                price = broker.execution_price(side=side, series=synthetic_series, index=0)
                if price <= 0:
                    signals.append({
                        "id": len(signals) + 1,
                        "figi": figi,
                        "signal_type": side.lower(),
                        "bar_time": bar_time,
                        "price": None,
                        "was_executed": 0,
                        "reason": "no_execution_price",
                    })
                    continue
                signals.append({
                    "id": len(signals) + 1,
                    "figi": figi,
                    "signal_type": side.lower(),
                    "bar_time": bar_time,
                    "price": round(price, 6),
                    "was_executed": 0,
                })

                if side == "BUY" and figi not in open_figis:
                    if pause_entries_today or day_block_new_buys:
                        signals[-1]["reason"] = "blocked_pause_day_or_daily_loss_cap"
                        continue
                    if allowed_today is not None and figi.upper() not in allowed_today:
                        signals[-1]["reason"] = "not_in_daily_candidates"
                        continue
                    eff_cash = compute_effective_free_funds(cash, reserve_pct)
                    rb_cap = _risk_budget_max_quantity(
                        portfolio_value=equity_pre,
                        entry_price=price,
                        risk_per_trade_pct=risk_pt,
                        stop_loss_pct=stop_pct,
                    )
                    qty, cash_after_buy, comm = executor.execute_buy(
                        cash=cash,
                        price=price,
                        risk_params=risk,
                        portfolio_value=equity_pre,
                        cost_kw=cost_kw,
                        free_funds_for_sizing=eff_cash,
                        risk_budget_max_quantity=rb_cap,
                    )
                    if qty <= 0:
                        signals[-1]["reason"] = "rejected_position_size"
                        continue
                    cash = cash_after_buy
                    positions[figi] = _Position(figi=figi, quantity=qty, entry_price=price, side="buy", peak_price=price)
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
                    signals[-1]["was_executed"] = 1
                    signals[-1]["reason"] = "executed"
                elif side == "SELL" and figi in open_figis:
                    pos = positions.pop(figi)
                    tc = TradingCosts(pos.entry_price, pos.quantity, is_buy=False, **cost_kw)
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
                    signals[-1]["was_executed"] = 1
                    signals[-1]["reason"] = "executed"
                    open_figis.discard(figi)
                else:
                    signals[-1]["reason"] = "ignored_signal_state"

            price_by_figi: Dict[str, float] = {}
            for figi, _pos in positions.items():
                px_m = _close_at_or_before(
                    full_series_by_figi.get(figi, []),
                    times_by_figi.get(figi, []),
                    bar_time,
                )
                if px_m > 0:
                    price_by_figi[figi] = px_m
            mark_equity = portfolio.mark_to_market(cash=cash, positions=positions, price_by_figi=price_by_figi)
            if i_bt % equity_sample_stride == 0 or i_bt == len(day_times) - 1:
                equity_curve.append({"time": bar_time, "equity": round(mark_equity, 2)})
            if mark_equity > peak_equity:
                peak_equity = mark_equity
            if peak_equity > 0:
                dd = (peak_equity - mark_equity) / peak_equity * 100.0
                if max_dd_pct is None or dd > max_dd_pct:
                    max_dd_pct = dd

            await asyncio.sleep(0)
            bars_processed += 1
            if progress_callback_sync is not None and bars_total > 0:
                if bars_processed % 24 == 0 or bars_processed >= bars_total:
                    try:
                        progress_callback_sync(bars_processed, bars_total)
                    except Exception:
                        pass

        last_bar_time = day_times[-1] if day_times else ""
        if force_flatten and positions and last_bar_time:
            for figi_fc in list(positions.keys()):
                pos_fc = positions.get(figi_fc)
                if not pos_fc:
                    continue
                px_fc = _close_at_or_before(
                    full_series_by_figi.get(figi_fc, []),
                    times_by_figi.get(figi_fc, []),
                    last_bar_time,
                )
                if px_fc <= 0:
                    continue
                positions.pop(figi_fc, None)
                tcf = TradingCosts(pos_fc.entry_price, pos_fc.quantity, is_buy=False, **cost_kw)
                actf = tcf.calculate_actual_profit(px_fc)
                cash += px_fc * pos_fc.quantity - actf["commission_sell"] - actf["tax"]
                trades.append({
                    "id": len(trades) + 1,
                    "figi": figi_fc,
                    "side": "sell",
                    "bar_time": last_bar_time,
                    "price": round(px_fc, 6),
                    "quantity": pos_fc.quantity,
                    "commission": round(actf["commission_buy"] + actf["commission_sell"], 4),
                    "pnl_net": round(actf["net_profit"], 4),
                })
                signals.append({
                    "id": len(signals) + 1,
                    "figi": figi_fc,
                    "signal_type": "sell",
                    "bar_time": last_bar_time,
                    "price": round(px_fc, 6),
                    "was_executed": 1,
                    "reason": "force_market_flatten_eod",
                })

        if day_start_equity is not None:
            feod = float(cash)
            for figi_e, pos_e in positions.items():
                px_e = _close_at_or_before(
                    full_series_by_figi.get(figi_e, []),
                    times_by_figi.get(figi_e, []),
                    last_bar_time,
                )
                if px_e > 0:
                    feod += pos_e.quantity * px_e
            had_trades_today = any(str(t.get("bar_time") or "").startswith(day) for t in trades)
            if had_trades_today:
                if feod < day_start_equity:
                    consecutive_loss_days += 1
                else:
                    consecutive_loss_days = 0
                if streak_limit > 0 and consecutive_loss_days >= streak_limit:
                    cooling_no_new_entries = True
                    consecutive_loss_days = 0

        price_by_figi_eod: Dict[str, float] = {}
        for figi, _pos in positions.items():
            px_eod = _close_at_or_before(
                full_series_by_figi.get(figi, []),
                times_by_figi.get(figi, []),
                last_bar_time,
            )
            if px_eod > 0:
                price_by_figi_eod[figi] = px_eod
        daily_positions.extend(
            portfolio.end_of_day_positions(
                trade_date=day,
                positions=positions,
                price_by_figi=price_by_figi_eod,
            )
        )

    if progress_callback_sync is not None and bars_total > 0:
        try:
            progress_callback_sync(bars_total, bars_total)
        except Exception:
            pass

    final_equity = equity_curve[-1]["equity"] if equity_curve else float(initial_capital)
    ret_pct = (final_equity / float(initial_capital) - 1.0) * 100.0 if initial_capital else 0.0

    return BacktestResult(
        initial_capital=float(initial_capital),
        final_equity=float(final_equity),
        total_return_percent=round(ret_pct, 4),
        max_drawdown_percent=round(max_dd_pct, 4) if max_dd_pct is not None else None,
        trades=trades,
        equity_curve=equity_curve,
        signals=signals,
        daily_positions=daily_positions,
        cancelled=False,
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
