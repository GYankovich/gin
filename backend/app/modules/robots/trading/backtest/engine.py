"""
Бэктестинг стратегий на исторических свечах (без реальных сделок).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.modules.robots.trading.costs import (
    TradingCosts,
    resolve_robot_cost_rates,
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
    peak_price: float = 0.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _true_range(curr: Dict[str, Any], prev_close: Optional[float]) -> float:
    high = _close_price({"close": curr.get("high") or {}})
    low = _close_price({"close": curr.get("low") or {}})
    if high <= 0 and low <= 0:
        # fallback for malformed candles
        close = _close_price(curr)
        high = close
        low = close
    if prev_close is None or prev_close <= 0:
        return max(0.0, high - low)
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def _atr_percent(series: List[Dict[str, Any]], idx: int, period: int) -> Optional[float]:
    if idx <= 0:
        return None
    from_i = max(1, idx - max(1, period) + 1)
    trs: List[float] = []
    for j in range(from_i, idx + 1):
        prev_close = _close_price(series[j - 1]) if j - 1 >= 0 else None
        tr = _true_range(series[j], prev_close)
        if tr > 0:
            trs.append(tr)
    if not trs:
        return None
    close = _close_price(series[idx])
    if close <= 0:
        return None
    atr = sum(trs) / float(len(trs))
    return (atr / close) * 100.0


def _vwap(series: List[Dict[str, Any]], idx: int, lookback: int) -> Optional[float]:
    if idx < 0:
        return None
    start = max(0, idx - max(1, lookback) + 1)
    num = 0.0
    den = 0.0
    for j in range(start, idx + 1):
        c = _close_price(series[j])
        v = _safe_float(series[j].get("volume"), 0.0)
        if c <= 0 or v <= 0:
            continue
        num += c * v
        den += v
    if den <= 0:
        return None
    return num / den


def _entry_checks(
    *,
    side: str,
    series: List[Dict[str, Any]],
    idx: int,
    strategy_params: Dict[str, Any],
) -> Tuple[bool, str]:
    if side != "BUY":
        return True, "ok"
    price = _close_price(series[idx])
    if price <= 0:
        return False, "invalid_price"

    # 1) VWAP check (default enabled)
    use_vwap = bool(strategy_params.get("use_vwap_filter", True))
    if use_vwap:
        vwap_window = int(_safe_float(strategy_params.get("vwap_window", 20), 20))
        max_dev_pct = _safe_float(strategy_params.get("vwap_max_deviation_percent", 3.0), 3.0)
        vwap_val = _vwap(series, idx, vwap_window)
        if vwap_val is None:
            return False, "vwap_unavailable"
        dev_pct = abs(price - vwap_val) / vwap_val * 100.0 if vwap_val > 0 else 0.0
        if dev_pct > max_dev_pct:
            return False, f"vwap_deviation>{max_dev_pct}"

    # 2) Local minimum bounce check (default enabled)
    use_bounce = bool(strategy_params.get("use_local_min_bounce", True))
    if use_bounce:
        bounce_window = int(_safe_float(strategy_params.get("local_min_window", 12), 12))
        if idx < 1:
            return False, "not_enough_candles_for_bounce"
        from_i = max(0, idx - bounce_window)
        local_min = min(_close_price(series[j]) for j in range(from_i, idx))
        prev_close = _close_price(series[idx - 1])
        if prev_close > local_min:
            return False, "no_local_min_touch"
        if price <= prev_close:
            return False, "no_bounce_after_local_min"

    # 3) Green candle check (default enabled)
    use_green = bool(strategy_params.get("require_green_candle", True))
    if use_green:
        open_px = _close_price({"close": series[idx].get("open") or {}})
        if open_px > 0 and price <= open_px:
            return False, "not_green_candle"

    # 4) Volume check (default enabled)
    use_volume = bool(strategy_params.get("use_volume_filter", True))
    if use_volume:
        vol_window = int(_safe_float(strategy_params.get("volume_window", 20), 20))
        vol_mult = _safe_float(strategy_params.get("volume_min_multiplier", 1.0), 1.0)
        start = max(0, idx - vol_window)
        vols = [_safe_float(series[j].get("volume"), 0.0) for j in range(start, idx)]
        cur_vol = _safe_float(series[idx].get("volume"), 0.0)
        if not vols:
            return False, "volume_baseline_unavailable"
        avg_vol = sum(vols) / float(len(vols))
        if avg_vol <= 0:
            return False, "volume_baseline_zero"
        if cur_vol < avg_vol * vol_mult:
            return False, f"volume<{vol_mult}x_avg"

    # 5) ATR on 5m check (default enabled)
    use_atr = bool(strategy_params.get("use_atr5_filter", True))
    if use_atr:
        atr_period = int(_safe_float(strategy_params.get("atr5_period", 14), 14))
        atr_min_pct = _safe_float(strategy_params.get("atr5_min_percent", 0.1), 0.1)
        atr_pct = _atr_percent(series, idx, atr_period)
        if atr_pct is None:
            return False, "atr5_unavailable"
        if atr_pct < atr_min_pct:
            return False, f"atr5<{atr_min_pct}%"

    return True, "ok"


@dataclass
class BacktestResult:
    initial_capital: float
    final_equity: float
    total_return_percent: float
    max_drawdown_percent: Optional[float]
    trades: List[Dict[str, Any]] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    signals: List[Dict[str, Any]] = field(default_factory=list)
    daily_positions: List[Dict[str, Any]] = field(default_factory=list)


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

    for day in sorted(candles_by_day.keys()):
        day_map = candles_by_day.get(day) or {}
        day_figis = sorted(day_map.keys())
        if not day_figis:
            continue
        day_times = sorted({(_candle_time_iso(c) or "") for ff in day_figis for c in day_map.get(ff, []) if _candle_time_iso(c)})
        if not day_times:
            continue
        allowed_today = allowed_map.get(day) if day in allowed_map else None

        for bar_time in day_times:
            snap: Dict[str, List[Dict[str, Any]]] = {}
            for ff in day_figis:
                seq = [x for x in full_series_by_figi.get(ff, []) if _candle_time_iso(x) <= bar_time]
                if len(seq) >= warmup:
                    snap[ff] = seq
            if not snap:
                continue
            raw_signals = await strategy.generate_signals(snap)

            portfolio_value = cash
            for figi, pos in positions.items():
                seq_pos = [x for x in full_series_by_figi.get(figi, []) if _candle_time_iso(x) <= bar_time]
                if seq_pos:
                    portfolio_value += pos.quantity * _close_price(seq_pos[-1])
            equity_pre = portfolio_value
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
                    if allowed_today is not None and figi.upper() not in allowed_today:
                        signals[-1]["reason"] = "not_in_daily_candidates"
                        continue
                    ok, reason = _entry_checks(side="BUY", series=seq, idx=idx_local, strategy_params=sp)
                    if not ok:
                        signals[-1]["reason"] = reason
                        continue
                    qty, cash_after_buy, comm = executor.execute_buy(
                        cash=cash,
                        price=price,
                        risk_params=risk,
                        portfolio_value=equity_pre,
                        cost_kw=cost_kw,
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

            trailing_stop_pct = _safe_float(sp.get("trailing_stop_percent", 0.0), 0.0)
            if trailing_stop_pct > 0:
                for figi in list(positions.keys()):
                    pos = positions.get(figi)
                    if not pos:
                        continue
                    seq_pos = [x for x in full_series_by_figi.get(figi, []) if _candle_time_iso(x) <= bar_time]
                    if not seq_pos:
                        continue
                    px = _close_price(seq_pos[-1])
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

            price_by_figi: Dict[str, float] = {}
            for figi, _pos in positions.items():
                seq_pos = [x for x in full_series_by_figi.get(figi, []) if _candle_time_iso(x) <= bar_time]
                if seq_pos:
                    price_by_figi[figi] = _close_price(seq_pos[-1])
            mark_equity = portfolio.mark_to_market(cash=cash, positions=positions, price_by_figi=price_by_figi)
            equity_curve.append({"time": bar_time, "equity": round(mark_equity, 2)})
            if mark_equity > peak_equity:
                peak_equity = mark_equity
            if peak_equity > 0:
                dd = (peak_equity - mark_equity) / peak_equity * 100.0
                if max_dd_pct is None or dd > max_dd_pct:
                    max_dd_pct = dd

        last_bar_time = day_times[-1] if day_times else ""
        price_by_figi_eod: Dict[str, float] = {}
        for figi, _pos in positions.items():
            seq_pos = [x for x in full_series_by_figi.get(figi, []) if _candle_time_iso(x) <= last_bar_time]
            if seq_pos:
                price_by_figi_eod[figi] = _close_price(seq_pos[-1])
        daily_positions.extend(
            portfolio.end_of_day_positions(
                trade_date=day,
                positions=positions,
                price_by_figi=price_by_figi_eod,
            )
        )

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
