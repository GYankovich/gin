"""
Unified history backtest — DEPRECATED (этап 3 BRD-ARCH-04).

Prod: `trading/runtime/orchestrator.py` → `TradingOrchestrator.run_backtest_replay`.
Не импортировать из application code; только legacy parity-эксперименты.
"""

from __future__ import annotations

import asyncio
import warnings
import bisect
import logging
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.modules.robots.trading.backtest.engine import (
    BacktestResult as LegacyBacktestResult,
    _bar_in_trading_session,
    _candle_time_iso,
    _run_generate_signals_blocking,
    _series_prefix_tail_for_bar,
    _session_time_from_risk,
)
from app.modules.robots.trading.contracts import Candle, Order, Signal
from app.modules.robots.trading.data_provider.preloaded import PreloadedHistoricalDataProvider
from app.modules.robots.trading.engines.context import RuntimeContext
from app.modules.robots.trading.engines.trading_loop import apply_fill_to_context
from app.modules.robots.trading.execution.sim import SimExecution
from app.modules.robots.trading.pipeline.runner import PipelineRunner
from app.modules.robots.trading.recorder import MemoryRecorder
from app.modules.robots.trading.risk import RiskManager, RiskParams
from app.modules.robots.trading.strategies import get_strategy_class
from app.modules.robots.trading.costs import resolve_robot_cost_rates

logger = logging.getLogger(__name__)

# grain_seed — отдельный legacy-конвейер (orchestrator, cooling)
LEGACY_ONLY_STRATEGIES = frozenset({"grain_seed"})


def should_use_unified_engine(strategy_name: str) -> bool:
    return str(strategy_name or "").strip().lower() not in LEGACY_ONLY_STRATEGIES


async def run_unified_history_backtest(
    *,
    db: Session,
    candles_by_figi: Dict[str, List[Dict[str, Any]]],
    allowed_figis_by_date: Dict[str, List[str]],
    strategy_name: str,
    strategy_params: Dict[str, Any],
    risk_params: Dict[str, Any],
    pipeline_filters: List[Dict[str, Any]],
    pipeline_mode: str,
    robot_config: Dict[str, Any],
    initial_capital: float,
    board: str = "TQBR",
    intraday_interval: str = "M5",
    execution_model: str = "NEXT_BAR_OPEN",
    slippage_pct: float = 0.0,
    cancel_check: Optional[Callable[[], Awaitable[bool]]] = None,
    cancel_check_sync: Optional[Callable[[], bool]] = None,
    progress_callback_sync: Optional[Callable[[int, int], None]] = None,
) -> LegacyBacktestResult:
    """Симуляция через unified stack (RiskManager + SimExecution + strategy)."""
    warnings.warn(
        "run_unified_history_backtest is deprecated; use TradingOrchestrator.run_backtest_replay",
        DeprecationWarning,
        stacklevel=2,
    )
    figis = list(candles_by_figi.keys())
    if not figis:
        raise ValueError("Нет свечей")

    sp = dict(strategy_params)
    sp["figis"] = figis
    strategy_class = get_strategy_class(strategy_name)
    strategy = strategy_class(None, sp)

    try:
        warmup = int(await strategy.get_required_candles_count())
    except Exception:
        warmup = 50
    warmup = max(2, warmup)
    tail_keep = max(warmup + 200, int(sp.get("sim_indicator_tail", 960) or 960))

    br, ndfl = resolve_robot_cost_rates(robot_config)
    risk = RiskManager(RiskParams.from_legacy_dict(risk_params))
    recorder = MemoryRecorder()
    data = PreloadedHistoricalDataProvider(
        db, board=board, candles_by_ticker=candles_by_figi, interval_label=intraday_interval,
    )
    ctx = RuntimeContext(
        mode="BACKTEST",
        data=data,
        pipeline=PipelineRunner(pipeline_filters, mode=pipeline_mode),
        strategy=strategy,
        risk=risk,
        execution=SimExecution(
            execution_model=execution_model,
            slippage_pct=slippage_pct,
            commission_rate=br,
            ndfl_rate=ndfl,
        ),
        recorder=recorder,
        robot_config=robot_config,
    )
    ctx.cash = float(initial_capital)
    ctx.equity = float(initial_capital)
    ctx.allowed_figis_by_date = {
        str(k): [str(x).upper() for x in (v or []) if x]
        for k, v in (allowed_figis_by_date or {}).items()
    }

    # --- group candles by day (same as legacy engine) ---
    candles_by_day: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    full_series: Dict[str, List[Dict[str, Any]]] = {}
    times_by_figi: Dict[str, List[str]] = {}
    for f in figis:
        series_full = sorted(list(candles_by_figi.get(f, [])), key=_candle_time_iso)
        full_series[f] = series_full
        times_by_figi[f] = [_candle_time_iso(c) for c in series_full]
        for c in series_full:
            t = _candle_time_iso(c)
            if not t or len(t) < 10:
                continue
            candles_by_day.setdefault(t[:10], {}).setdefault(f, []).append(c)

    session_start = _session_time_from_risk(risk_params.get("trading_hours_start"), "10:00")
    session_end = _session_time_from_risk(risk_params.get("trading_hours_end"), "18:45")

    bars_total = 0
    for day in sorted(candles_by_day.keys()):
        dm = candles_by_day.get(day) or {}
        figs = sorted(dm.keys())
        if not figs:
            continue
        times = sorted({(_candle_time_iso(c) or "") for ff in figs for c in dm.get(ff, []) if _candle_time_iso(c)})
        times = [bt for bt in times if _bar_in_trading_session(bt, session_start, session_end)]
        bars_total += len(times)

    bars_processed = 0
    equity_curve: List[Dict[str, Any]] = []
    peak_equity = float(initial_capital)
    max_dd_pct: Optional[float] = None

    if progress_callback_sync and bars_total > 0:
        try:
            progress_callback_sync(0, bars_total)
        except Exception:
            pass

    for day in sorted(candles_by_day.keys()):
        if cancel_check_sync and cancel_check_sync():
            return _legacy_result(ctx, initial_capital, equity_curve, max_dd_pct, cancelled=True, recorder=recorder)
        if cancel_check:
            try:
                if await cancel_check():
                    return _legacy_result(ctx, initial_capital, equity_curve, max_dd_pct, cancelled=True, recorder=recorder)
            except Exception:
                pass

        day_map = candles_by_day.get(day) or {}
        allowed_today = set(ctx.allowed_figis_by_date.get(day, []))
        day_figis = sorted(f for f in day_map.keys() if not allowed_today or f.upper() in allowed_today)
        if not day_figis:
            continue

        day_times = sorted({(_candle_time_iso(c) or "") for ff in day_figis for c in day_map.get(ff, []) if _candle_time_iso(c)})
        day_times = [bt for bt in day_times if _bar_in_trading_session(bt, session_start, session_end)]
        if not day_times:
            continue

        ctx.risk.begin_day(equity_at_open=ctx.equity)
        day_date = date.fromisoformat(day)

        for bar_time in day_times:
            bars_processed += 1
            if progress_callback_sync and bars_total > 0:
                if bars_processed % 48 == 0 or bars_processed == bars_total:
                    try:
                        progress_callback_sync(bars_processed, bars_total)
                    except Exception:
                        pass

            # mark-to-market + exits (как live tick)
            for sid in list(ctx.positions.keys()):
                series = full_series.get(sid) or []
                times = times_by_figi.get(sid) or []
                idx = bisect.bisect_right(times, bar_time) - 1
                if idx < 0:
                    continue
                ctx.positions[sid].current_price = float(_parse_close(series[idx]))
                bar_candle = _dict_to_candle(series[idx], sid, intraday_interval)
                exit_sig = ctx.risk.evaluate_exits(ctx.positions[sid], bar_candle)
                if exit_sig is not None:
                    await _execute_unified_signal(ctx, exit_sig, full_series, times_by_figi, bar_time, day_date, recorder)

            # strategy signals on bar close
            snap: Dict[str, List[Dict[str, Any]]] = {}
            for ff in day_figis:
                prefix = _series_prefix_tail_for_bar(
                    series=full_series.get(ff) or [],
                    times=times_by_figi.get(ff) or [],
                    bar_time=bar_time,
                    warmup=warmup,
                    tail_keep=tail_keep,
                )
                if prefix:
                    snap[ff] = prefix

            if not snap:
                continue

            raw = await asyncio.to_thread(_run_generate_signals_blocking, strategy, snap)
            for figi, side in (raw or {}).items():
                if side is None or str(figi).upper() not in allowed_today:
                    continue
                series = full_series.get(figi) or []
                times = times_by_figi.get(figi) or []
                idx = bisect.bisect_right(times, bar_time) - 1
                if idx < 0:
                    continue
                bar = series[idx]
                sig = Signal(
                    signal_id=uuid4(),
                    secid=figi,
                    figi=figi,
                    side="BUY" if str(side).upper() == "BUY" else "SELL",
                    target_price=float(_parse_close(bar)),
                    price_at_signal=float(_parse_close(bar)),
                    bar_time=bar_time,
                    strategy=strategy_name,
                    reason=f"strategy.{str(side).lower()}",
                )
                await recorder.record_signal(sig)

                if sig.side == "BUY":
                    decision = ctx.risk.pre_trade_check(sig, cash=ctx.cash, equity=ctx.equity, positions=ctx.positions)
                    if not decision.allow:
                        await recorder.record_risk_reject(sig, decision.reason)
                        continue
                    sig.quantity_hint = decision.quantity
                else:
                    pos = ctx.positions.get(figi)
                    if pos is None or pos.quantity <= 0:
                        continue
                    sig.quantity_hint = pos.quantity

                await _execute_unified_signal(ctx, sig, full_series, times_by_figi, bar_time, day_date, recorder)

            eq = ctx.equity
            equity_curve.append({"time": bar_time, "equity": eq})
            if eq > peak_equity:
                peak_equity = eq
            if peak_equity > 0:
                dd = (peak_equity - eq) / peak_equity * 100.0
                if max_dd_pct is None or dd > max_dd_pct:
                    max_dd_pct = dd

        # EOD flatten (как live end-of-day)
        if ctx.positions:
            last_t = day_times[-1]
            try:
                eod_dt = datetime.fromisoformat(last_t.replace("Z", "+00:00"))
            except Exception:
                eod_dt = datetime.now(timezone.utc)
            for sig in ctx.risk.force_close_signals(eod_dt, ctx.positions):
                await recorder.record_signal(sig)
                await _execute_unified_signal(ctx, sig, full_series, times_by_figi, last_t, day_date, recorder)

        ctx.risk.end_day(equity_at_close=ctx.equity, had_trades_today=bool(ctx.trade_log))

    return _legacy_result(ctx, initial_capital, equity_curve, max_dd_pct, cancelled=False, recorder=recorder)


async def _execute_unified_signal(
    ctx: RuntimeContext,
    sig: Signal,
    full_series: Dict[str, List[Dict[str, Any]]],
    times_by_figi: Dict[str, List[str]],
    bar_time: str,
    day: date,
    recorder: MemoryRecorder,
) -> None:
    series = full_series.get(sig.secid) or []
    times = times_by_figi.get(sig.secid) or []
    idx = bisect.bisect_right(times, bar_time) - 1
    if idx < 0:
        return
    side = sig.side.upper()
    if side == "CLOSE":
        pos = ctx.positions.get(sig.secid)
        if pos is None or pos.quantity <= 0:
            return
        order_side = "SELL" if pos.side == "LONG" else "BUY"
        qty = pos.quantity
    else:
        order_side = "BUY" if side == "BUY" else "SELL"
        qty = int(sig.quantity_hint or 0)
    order = Order(
        secid=sig.secid,
        figi=sig.figi or sig.secid,
        side=order_side,
        type="MARKET",
        quantity=qty,
        price=sig.target_price,
        signal_id=sig.signal_id,
    )
    if order.quantity <= 0:
        return
    result = await ctx.execution.submit(order, series=series, index=idx)
    await recorder.record_order(result.order)
    if not result.accepted or result.fill is None:
        return
    await recorder.record_fill(result.fill)
    exec_sig = sig.model_copy(update={"side": order_side})
    apply_fill_to_context(ctx, exec_sig, result.fill, day=day)


def _parse_close(candle: Dict[str, Any]) -> float:
    cl = candle.get("close") or {}
    if isinstance(cl, (int, float)):
        return float(cl)
    return float(int(cl.get("units", 0) or 0)) + float(int(cl.get("nano", 0) or 0)) / 1e9


def _dict_to_candle(raw: Dict[str, Any], secid: str, interval: str) -> Candle:
    return Candle.from_tinvest_dict(raw, interval=interval, figi=secid)


def _legacy_result(
    ctx: RuntimeContext,
    initial_capital: float,
    equity_curve: List[Dict[str, Any]],
    max_dd_pct: Optional[float],
    *,
    cancelled: bool,
    recorder: MemoryRecorder,
) -> LegacyBacktestResult:
    final_equity = ctx.equity
    ret_pct = (final_equity / float(initial_capital) - 1.0) * 100.0 if initial_capital else 0.0
    signals = [
        {
            "figi": s.figi or s.secid,
            "signal_type": s.side.lower(),
            "price_at_signal": s.price_at_signal,
            "bar_time": s.bar_time,
            "was_executed": any(
                t.get("figi") == (s.figi or s.secid) and t.get("bar_time") == s.bar_time
                for t in ctx.trade_log
            ),
            "reason": s.reason,
        }
        for s in recorder.signals
    ]
    return LegacyBacktestResult(
        initial_capital=float(initial_capital),
        final_equity=float(final_equity),
        total_return_percent=round(ret_pct, 4),
        max_drawdown_percent=round(max_dd_pct, 4) if max_dd_pct is not None else None,
        trades=list(ctx.trade_log),
        equity_curve=equity_curve,
        signals=signals,
        daily_positions=[],
        cancelled=cancelled,
    )


__all__ = ["run_unified_history_backtest", "should_use_unified_engine", "LEGACY_ONLY_STRATEGIES"]
