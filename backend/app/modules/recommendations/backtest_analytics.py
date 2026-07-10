from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional

MOEX_FULL_SESSION_START_MIN = 10 * 60
MOEX_FULL_SESSION_END_MIN = 18 * 60 + 45
_WEEKDAY_BITS = (1, 2, 4, 8, 16, 32, 64)


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def exit_reason_metrics(trades: List[Any], signals: List[Any]) -> Dict[str, Optional[float]]:
    stop_hits = 0
    tp_hits = 0
    for s in signals:
        if not isinstance(s, dict):
            continue
        if int(s.get("was_executed") or 0) != 1:
            continue
        sig_type = str(s.get("signal_type") or "").lower()
        if sig_type not in ("sell", "close"):
            continue
        reason = str(s.get("reason") or "").lower()
        if reason in ("stop_loss", "trailing_stop_executed"):
            stop_hits += 1
        elif reason == "take_profit":
            tp_hits += 1

    closed_trades = [
        t
        for t in trades
        if isinstance(t, dict)
        and t.get("pnl_net") is not None
        and str(t.get("side") or "").lower() in ("sell", "close")
    ]
    total_closed = len(closed_trades)
    if total_closed < 3:
        return {"stopLossHitRate": None, "takeProfitHitRate": None}

    if stop_hits + tp_hits > 0:
        denom = max(total_closed, stop_hits + tp_hits)
        return {
            "stopLossHitRate": round(stop_hits / denom * 100.0, 2),
            "takeProfitHitRate": round(tp_hits / denom * 100.0, 2),
        }

    loss_closes = sum(1 for t in closed_trades if float(t.get("pnl_net") or 0) < 0)
    win_closes = sum(1 for t in closed_trades if float(t.get("pnl_net") or 0) > 0)
    return {
        "stopLossHitRate": round(loss_closes / total_closed * 100.0, 2),
        "takeProfitHitRate": round(win_closes / total_closed * 100.0, 2),
    }


def universe_metrics(payload: Dict[str, Any], trades: List[Any]) -> Dict[str, Optional[float]]:
    daily = payload.get("daily_summary") if isinstance(payload.get("daily_summary"), list) else []
    universe_sizes: List[int] = []
    for row in daily:
        if not isinstance(row, dict):
            continue
        accept = int(row.get("candidates_accept") or 0)
        reject = int(row.get("candidates_reject") or 0)
        total = accept + reject
        if total > 0:
            universe_sizes.append(total)
        elif accept > 0:
            universe_sizes.append(accept)

    avg_universe = (sum(universe_sizes) / len(universe_sizes)) if universe_sizes else None
    figis = {
        str(t.get("figi")).upper()
        for t in trades
        if isinstance(t, dict) and t.get("figi")
    }
    instruments_traded = float(len(figis))
    utilization = None
    if avg_universe is not None and avg_universe > 0:
        utilization = instruments_traded / avg_universe
    return {
        "avgUniverseSize": avg_universe,
        "instrumentsTraded": instruments_traded if instruments_traded > 0 else None,
        "universeUtilizationRatio": utilization,
    }


def _parse_msk_minutes(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    part = str(raw).strip().split()[0]
    m = re.match(r"^(\d{1,2}):(\d{2})$", part)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def gap_metrics_from_decisions(decisions_rows: List[Any]) -> Dict[str, Optional[float]]:
    gap_values: List[float] = []
    gap_rejects = 0
    for dr in decisions_rows:
        if not isinstance(dr, dict):
            continue
        eval_payload = dr.get("payload") if isinstance(dr.get("payload"), dict) else {}
        eval_obj = eval_payload.get("eval") if isinstance(eval_payload, dict) else {}
        gap_pct = _to_float(eval_obj.get("gap_percent"))
        if gap_pct is not None:
            gap_values.append(abs(gap_pct))
        if str(dr.get("result") or "").upper() == "REJECT":
            reason = str(dr.get("reason") or "").lower()
            if "гэп" in reason or "gap" in reason:
                gap_rejects += 1
    avg_gap = (sum(gap_values) / len(gap_values)) if gap_values else None
    return {
        "avgGapImpactPct": round(avg_gap, 4) if avg_gap is not None else None,
        "gapRejectCount": float(gap_rejects) if gap_rejects > 0 else None,
    }


def _estimate_ndfl_amount(trades: List[Any], ndfl_rate: float) -> Optional[float]:
    rate = max(0.0, float(ndfl_rate or 0))
    if rate <= 0 or rate >= 1:
        return 0.0 if rate == 0 else None
    total = 0.0
    found = False
    for t in trades:
        if not isinstance(t, dict):
            continue
        tax = _to_float(t.get("tax"))
        if tax is not None and tax > 0:
            total += tax
            found = True
            continue
        pnl = _to_float(t.get("pnl_net"))
        if pnl is None or pnl <= 0:
            continue
        if str(t.get("side") or "").lower() not in ("sell", "close"):
            continue
        gross = pnl / (1.0 - rate)
        total += gross - pnl
        found = True
    return round(total, 2) if found else None


def _weekday_return_metrics(equity_curve: List[Any]) -> Dict[str, Optional[float]]:
    by_date: Dict[str, float] = {}
    for p in equity_curve:
        if not isinstance(p, dict):
            continue
        t = str(p.get("time") or "")
        if len(t) < 10:
            continue
        eq = _to_float(p.get("equity"))
        if eq is not None:
            by_date[t[:10]] = eq
    if len(by_date) < 3:
        return {
            "negativeWeekdaysCount": None,
            "worstWeekdayReturnPct": None,
            "worstWeekdayBit": None,
        }

    dates = sorted(by_date.keys())
    daily_returns: Dict[str, float] = {}
    for i in range(1, len(dates)):
        prev_eq = by_date[dates[i - 1]]
        cur_eq = by_date[dates[i]]
        if prev_eq > 0:
            daily_returns[dates[i]] = (cur_eq - prev_eq) / prev_eq * 100.0

    weekday_vals: Dict[int, List[float]] = defaultdict(list)
    for d, ret in daily_returns.items():
        try:
            wd = date.fromisoformat(d).weekday()
        except ValueError:
            continue
        weekday_vals[wd].append(ret)

    weekday_avg: Dict[int, float] = {}
    for wd, vals in weekday_vals.items():
        if len(vals) >= 2:
            weekday_avg[wd] = sum(vals) / len(vals)

    if not weekday_avg:
        return {
            "negativeWeekdaysCount": None,
            "worstWeekdayReturnPct": None,
            "worstWeekdayBit": None,
        }

    negative_count = sum(1 for avg in weekday_avg.values() if avg < 0)
    worst_wd = min(weekday_avg, key=lambda k: weekday_avg[k])
    worst_bit = _WEEKDAY_BITS[worst_wd] if 0 <= worst_wd < len(_WEEKDAY_BITS) else None
    return {
        "negativeWeekdaysCount": float(negative_count),
        "worstWeekdayReturnPct": round(weekday_avg[worst_wd], 4),
        "worstWeekdayBit": float(worst_bit) if worst_bit is not None else None,
    }


def moex_metrics(
    payload: Dict[str, Any],
    trades: List[Any],
    *,
    risk_config: Optional[Dict[str, Any]] = None,
    costs_config: Optional[Dict[str, Any]] = None,
    decisions_rows: Optional[List[Any]] = None,
) -> Dict[str, Optional[float]]:
    risk_config = risk_config if isinstance(risk_config, dict) else {}
    costs_config = costs_config if isinstance(costs_config, dict) else {}
    history_stats = payload.get("history_stats") if isinstance(payload.get("history_stats"), dict) else {}

    gap_m = gap_metrics_from_decisions(decisions_rows or [])
    if history_stats.get("avgGapImpactPct") is not None:
        gap_m["avgGapImpactPct"] = _to_float(history_stats.get("avgGapImpactPct"))

    start_min = _parse_msk_minutes(risk_config.get("trading_hours_start"))
    end_min = _parse_msk_minutes(risk_config.get("trading_hours_end"))
    trading_hours_ratio = None
    if start_min is not None and end_min is not None and end_min > start_min:
        configured = end_min - start_min
        available = MOEX_FULL_SESSION_END_MIN - MOEX_FULL_SESSION_START_MIN
        if available > 0:
            trading_hours_ratio = round(configured / available, 4)
    if history_stats.get("tradingHoursUsedRatio") is not None:
        trading_hours_ratio = _to_float(history_stats.get("tradingHoursUsedRatio"))

    ndfl_rate = _to_float(costs_config.get("ndfl_rate"))
    if ndfl_rate is None:
        ndfl_rate = _to_float(risk_config.get("ndfl_rate"))
    ndfl_amount = _estimate_ndfl_amount(trades, ndfl_rate or 0.0)
    if history_stats.get("ndflAmount") is not None:
        ndfl_amount = _to_float(history_stats.get("ndflAmount"))

    initial_capital = _to_float(payload.get("initial_capital"))
    total_return_pct = _to_float(payload.get("total_return_percent"))
    ndfl_to_return_ratio = None
    if ndfl_amount is not None and initial_capital and total_return_pct is not None:
        return_rub = initial_capital * total_return_pct / 100.0
        if abs(return_rub) > 1e-6:
            ndfl_to_return_ratio = ndfl_amount / abs(return_rub)

    equity_curve = payload.get("equity_curve") if isinstance(payload.get("equity_curve"), list) else []
    weekday_m = _weekday_return_metrics(equity_curve)
    if history_stats.get("negativeWeekdaysCount") is not None:
        weekday_m["negativeWeekdaysCount"] = _to_float(history_stats.get("negativeWeekdaysCount"))
    if history_stats.get("worstWeekdayReturnPct") is not None:
        weekday_m["worstWeekdayReturnPct"] = _to_float(history_stats.get("worstWeekdayReturnPct"))
    if history_stats.get("worstWeekdayBit") is not None:
        weekday_m["worstWeekdayBit"] = _to_float(history_stats.get("worstWeekdayBit"))

    allowed_mask = _to_float(risk_config.get("allowed_weekdays"))
    all_weekdays_enabled = None
    if allowed_mask is not None:
        all_weekdays_enabled = 1.0 if int(allowed_mask) >= 31 else 0.0

    return {
        **gap_m,
        "tradingHoursUsedRatio": trading_hours_ratio,
        "ndflAmount": ndfl_amount,
        "ndflToReturnRatio": round(ndfl_to_return_ratio, 4) if ndfl_to_return_ratio is not None else None,
        "allowedWeekdaysMask": allowed_mask,
        "allWeekdaysEnabled": all_weekdays_enabled,
        **weekday_m,
    }


def _estimate_total_slippage(trades: List[Any], slippage_pct: float) -> float:
    rate = max(0.0, float(slippage_pct or 0))
    total = 0.0
    for t in trades:
        if not isinstance(t, dict):
            continue
        px = _to_float(t.get("price")) or 0.0
        qty = _to_float(t.get("quantity")) or 0.0
        if px > 0 and qty > 0:
            total += px * qty * rate / 100.0
    return round(total, 2)


def _estimate_leverage_used(
    trades: List[Any],
    equity_curve: List[Any],
    margin_summary: Dict[str, Any],
    initial_capital: Optional[float],
) -> Optional[float]:
    enabled = bool(margin_summary.get("enabled"))
    if not enabled:
        return 1.0
    equities = [
        _to_float(p.get("equity"))
        for p in equity_curve
        if isinstance(p, dict) and _to_float(p.get("equity")) is not None
    ]
    avg_equity = (sum(equities) / len(equities)) if equities else initial_capital
    peak_notional = 0.0
    for t in trades:
        if not isinstance(t, dict):
            continue
        if str(t.get("side") or "").lower() not in ("buy", "long"):
            continue
        px = _to_float(t.get("price")) or 0.0
        qty = _to_float(t.get("quantity")) or 0.0
        peak_notional = max(peak_notional, px * qty)
    if avg_equity and avg_equity > 0 and peak_notional > 0:
        configured = _to_float(margin_summary.get("leverage")) or 1.0
        used = peak_notional / avg_equity
        return round(min(used, configured), 4)
    configured = _to_float(margin_summary.get("leverage"))
    return configured if configured is not None else 1.0


def bybit_metrics(
    payload: Dict[str, Any],
    trades: List[Any],
    *,
    config: Optional[Dict[str, Any]] = None,
    slippage_pct: float = 0.0,
) -> Dict[str, Optional[float]]:
    config = config if isinstance(config, dict) else {}
    history_stats = payload.get("history_stats") if isinstance(payload.get("history_stats"), dict) else {}
    costs = config.get("costs") if isinstance(config.get("costs"), dict) else {}
    bybit_cfg = config.get("bybit") if isinstance(config.get("bybit"), dict) else {}
    exec_cfg = config.get("execution_model") if isinstance(config.get("execution_model"), dict) else {}
    margin_summary = payload.get("margin_summary") if isinstance(payload.get("margin_summary"), dict) else {}

    slip_pct = _to_float(slippage_pct)
    if slip_pct is None:
        slip_pct = _to_float(exec_cfg.get("slippage_pct")) or 0.0

    total_slippage = _estimate_total_slippage(trades, slip_pct or 0.0)
    if history_stats.get("totalSlippage") is not None:
        total_slippage = float(history_stats.get("totalSlippage"))

    initial_capital = _to_float(payload.get("initial_capital"))
    total_return_pct = _to_float(payload.get("total_return_percent"))
    slippage_to_return_ratio = None
    if initial_capital and total_return_pct is not None:
        return_rub = initial_capital * total_return_pct / 100.0
        if abs(return_rub) > 1e-6:
            slippage_to_return_ratio = total_slippage / abs(return_rub)

    equity_curve = payload.get("equity_curve") if isinstance(payload.get("equity_curve"), list) else []
    risk_cfg = config.get("risk") if isinstance(config.get("risk"), dict) else {}
    leverage_used = _estimate_leverage_used(trades, equity_curve, margin_summary, initial_capital)
    if history_stats.get("leverageUsed") is not None:
        leverage_used = _to_float(history_stats.get("leverageUsed"))

    configured_leverage = _to_float(bybit_cfg.get("leverage"))
    if configured_leverage is None:
        configured_leverage = _to_float(risk_cfg.get("max_leverage"))

    instrument_category = str(bybit_cfg.get("instrument_category") or "linear").lower()
    funding_mode = str(costs.get("funding_mode") or "off").lower()
    backtest_execution = str(costs.get("backtest_execution") or "").lower()
    backtest_fee_model = str(costs.get("backtest_fee_model") or "").lower()

    return {
        "totalSlippage": total_slippage if total_slippage > 0 else None,
        "slippageToReturnRatio": round(slippage_to_return_ratio, 4) if slippage_to_return_ratio is not None else None,
        "leverageUsed": leverage_used,
        "configuredLeverage": configured_leverage,
        "marginEnabled": 1.0 if margin_summary.get("enabled") else 0.0,
        "instrumentIsPerp": 1.0 if instrument_category in ("linear", "inverse") else 0.0,
        "fundingModeIsAverage": 1.0 if funding_mode == "average" else 0.0,
        "backtestExecutionIsMarket": 1.0 if backtest_execution == "market_taker" else 0.0,
        "backtestFeeModelIsMakerTaker": 1.0 if backtest_fee_model == "maker_taker" else 0.0,
    }


_MARKET_REF_VOL_PCT = {"tinvest": 18.0, "bybit": 55.0}


def _bar_dt(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def long_short_metrics(trades: List[Any], signals: List[Any]) -> Dict[str, Optional[float]]:
    positions: Dict[str, str] = {}
    long_entries = 0
    short_entries = 0
    long_pnls: List[float] = []
    short_pnls: List[float] = []

    events: List[tuple[str, Dict[str, Any], datetime]] = []
    for s in signals:
        if isinstance(s, dict):
            events.append(("sig", s, _bar_dt(s.get("bar_time")) or datetime.min))
    for t in trades:
        if isinstance(t, dict) and t.get("pnl_net") is not None:
            events.append(("close", t, _bar_dt(t.get("bar_time")) or datetime.min))
    events.sort(key=lambda x: x[2])

    for kind, item, _ in events:
        if kind == "sig":
            if int(item.get("was_executed") or 0) != 1:
                continue
            figi = str(item.get("figi") or "").upper()
            if not figi:
                continue
            st = str(item.get("signal_type") or "").lower()
            if st in ("buy", "long"):
                positions[figi] = "long"
                long_entries += 1
            elif st == "short":
                positions[figi] = "short"
                short_entries += 1
            elif st == "sell" and figi not in positions:
                positions[figi] = "short"
                short_entries += 1
        else:
            figi = str(item.get("figi") or "").upper()
            pnl = _to_float(item.get("pnl_net"))
            if pnl is None or not figi:
                continue
            direction = positions.pop(figi, "long")
            if direction == "short":
                short_pnls.append(pnl)
            else:
                long_pnls.append(pnl)

    if not signals:
        for t in trades:
            if not isinstance(t, dict):
                continue
            side = str(t.get("side") or "").lower()
            if side in ("buy", "long"):
                long_entries += 1
            elif side in ("short",):
                short_entries += 1
            pnl = _to_float(t.get("pnl_net"))
            if pnl is None:
                continue
            if side in ("sell", "close"):
                long_pnls.append(pnl)

    avg_long = (sum(long_pnls) / len(long_pnls)) if long_pnls else None
    avg_short = (sum(short_pnls) / len(short_pnls)) if short_pnls else None

    long_bias_weak = None
    short_bias_weak = None
    if short_entries >= 1 and long_entries > short_entries * 2:
        if avg_long is not None and avg_short is not None and avg_long < avg_short:
            long_bias_weak = 1.0
    if long_entries >= 1 and short_entries > long_entries * 2:
        if avg_long is not None and avg_short is not None and avg_short < avg_long:
            short_bias_weak = 1.0

    return {
        "longTrades": float(long_entries) if long_entries > 0 else None,
        "shortTrades": float(short_entries) if short_entries > 0 else None,
        "avgProfitLong": round(avg_long, 4) if avg_long is not None else None,
        "avgProfitShort": round(avg_short, 4) if avg_short is not None else None,
        "longBiasWithWeakProfit": long_bias_weak,
        "shortBiasWithWeakProfit": short_bias_weak,
    }


def hourly_pnl_metrics(trades: List[Any]) -> Dict[str, Optional[float]]:
    by_hour: Dict[int, List[float]] = defaultdict(list)
    for t in trades:
        if not isinstance(t, dict):
            continue
        pnl = _to_float(t.get("pnl_net"))
        dt = _bar_dt(t.get("bar_time"))
        if pnl is None or dt is None:
            continue
        by_hour[dt.hour].append(pnl)

    hour_avg = {h: (sum(v) / len(v)) for h, v in by_hour.items() if len(v) >= 2}
    if not hour_avg:
        return {
            "negativeHoursCount": None,
            "worstHourReturn": None,
            "worstTradingHour": None,
            "bestHourReturn": None,
            "bestTradingHour": None,
        }

    negative_hours = sum(1 for avg in hour_avg.values() if avg < 0)
    worst_hour = min(hour_avg, key=lambda h: hour_avg[h])
    best_hour = max(hour_avg, key=lambda h: hour_avg[h])
    return {
        "negativeHoursCount": float(negative_hours),
        "worstHourReturn": round(hour_avg[worst_hour], 4),
        "worstTradingHour": float(worst_hour),
        "bestHourReturn": round(hour_avg[best_hour], 4),
        "bestTradingHour": float(best_hour),
    }


def beta_estimate(volatility_annual_pct: Optional[float], broker_type: str) -> Optional[float]:
    vol = _to_float(volatility_annual_pct)
    if vol is None:
        return None
    ref = _MARKET_REF_VOL_PCT.get(str(broker_type or "").lower(), 20.0)
    if ref <= 0:
        return None
    return round(vol / ref, 4)


def general_metrics(
    payload: Dict[str, Any],
    trades: List[Any],
    signals: List[Any],
    *,
    broker_type: str = "tinvest",
    volatility_annual_pct: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    history_stats = payload.get("history_stats") if isinstance(payload.get("history_stats"), dict) else {}

    ls = long_short_metrics(trades, signals)
    hour_m = hourly_pnl_metrics(trades)
    vol = _to_float(volatility_annual_pct)
    if vol is None:
        vol = _to_float(history_stats.get("volatilityAnnualPct"))
    beta = beta_estimate(vol, broker_type)

    out: Dict[str, Optional[float]] = {
        **ls,
        **hour_m,
        "volatilityAnnualPct": round(vol, 4) if vol is not None else None,
        "betaEstimate": beta,
    }

    for key in list(out.keys()):
        if history_stats.get(key) is not None:
            out[key] = _to_float(history_stats.get(key))

    return out


def derive_payload_metrics(payload: Optional[Dict[str, Any]], best) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    trades = payload.get("trades") if isinstance(payload.get("trades"), list) else []
    signals = payload.get("signals") if isinstance(payload.get("signals"), list) else []
    fee = payload.get("fee_summary") if isinstance(payload.get("fee_summary"), dict) else {}
    history_stats = payload.get("history_stats") if isinstance(payload.get("history_stats"), dict) else {}

    closed_pnls: List[float] = []
    for t in trades:
        pnl = _to_float(t.get("pnl_net") if isinstance(t, dict) else None)
        if pnl is not None:
            closed_pnls.append(pnl)
    wins = [p for p in closed_pnls if p > 0]
    losses = [p for p in closed_pnls if p < 0]

    avg_win = (sum(wins) / len(wins)) if wins else None
    avg_loss = (abs(sum(losses)) / len(losses)) if losses else None
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    total_commission = _to_float(fee.get("total_commission"))
    if total_commission is None and trades:
        total_commission = sum(
            _to_float(t.get("commission")) or 0.0 for t in trades if isinstance(t, dict)
        )

    initial_capital = _to_float(payload.get("initial_capital"))
    total_return_pct = _to_float(best.total_return_percent if best else payload.get("total_return_percent"))
    commission_to_return_ratio = None
    if total_commission is not None and initial_capital and total_return_pct is not None:
        return_rub = initial_capital * total_return_pct / 100.0
        if abs(return_rub) > 1e-6:
            commission_to_return_ratio = total_commission / abs(return_rub)

    profit_loss_ratio = None
    if avg_win is not None and avg_loss is not None and avg_loss > 0:
        profit_loss_ratio = avg_win / avg_loss

    total_funding = _to_float(fee.get("total_funding"))
    funding_to_return_ratio = None
    if total_funding is not None and initial_capital and total_return_pct is not None:
        return_rub = initial_capital * total_return_pct / 100.0
        if abs(return_rub) > 1e-6:
            funding_to_return_ratio = abs(total_funding) / abs(return_rub)

    avg_profit_pct = None
    if avg_win is not None and initial_capital and initial_capital > 0:
        avg_profit_pct = round(avg_win / initial_capital * 100.0, 4)

    exit_m = exit_reason_metrics(trades, signals)
    if history_stats.get("stopLossHitRate") is not None:
        exit_m["stopLossHitRate"] = _to_float(history_stats.get("stopLossHitRate"))
    if history_stats.get("takeProfitHitRate") is not None:
        exit_m["takeProfitHitRate"] = _to_float(history_stats.get("takeProfitHitRate"))

    uni = universe_metrics(payload, trades)
    if history_stats.get("avgUniverseSize") is not None:
        uni["avgUniverseSize"] = _to_float(history_stats.get("avgUniverseSize"))
    if history_stats.get("instrumentsTraded") is not None:
        uni["instrumentsTraded"] = _to_float(history_stats.get("instrumentsTraded"))

    return {
        "profitFactor": profit_factor,
        "avgProfitPerTrade": avg_win,
        "avgLossPerTrade": avg_loss,
        "avgProfitPerTradePct": avg_profit_pct,
        "profitLossRatio": profit_loss_ratio,
        "totalCommission": total_commission,
        "commissionToReturnRatio": commission_to_return_ratio,
        "totalFunding": total_funding,
        "fundingToReturnRatio": funding_to_return_ratio,
        **exit_m,
        **uni,
    }
