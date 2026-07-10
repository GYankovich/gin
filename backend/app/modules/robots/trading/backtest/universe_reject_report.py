"""Детальный отчёт по отклонениям universe в файловый лог бэктеста."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.modules.robots.crypto_universe import ScreeningRow, resolve_crypto_universe_filters
from app.modules.robots.trading.backtest.run_file_logger import (
    _session_for,
    backtest_run_dir,
    log_backtest_run_info,
)


def _pct_str(value: Optional[float], *, digits: int = 4) -> Optional[str]:
    if value is None:
        return None
    return f"{float(value):.{digits}f}%"


def screening_row_to_reject_decision(
    row: ScreeningRow,
    *,
    trade_date: str,
    stage: str = "crypto_universe",
) -> Dict[str, Any]:
    return {
        "trade_date": trade_date,
        "stage": stage,
        "ticker": row.symbol,
        "result": "REJECT",
        "reason": row.reject_reason or "unknown",
        "turnover24h": row.turnover24h,
        "lastPrice": row.lastPrice,
        "spreadPercent": row.spreadPercent,
        "dailyRangePercent": row.dailyRangePercent,
        "avg_funding_rate": row.avg_funding_rate,
        "open_interest_usd": row.open_interest_usd,
        "lsr": row.lsr,
        "rvol": row.rvol,
        "atr_percent": row.atr_percent,
    }


def _filters_snapshot(config: Dict[str, Any], *, is_crypto: bool) -> Dict[str, Any]:
    if not is_crypto:
        pipeline = config.get("pipeline") if isinstance(config.get("pipeline"), dict) else {}
        return {
            "broker": str(config.get("broker_type") or "tinvest"),
            "universe_mode": config.get("universe_mode"),
            "pipeline_mode": pipeline.get("mode"),
            "pipeline_filters_count": len(pipeline.get("filters") or []),
        }
    flt = resolve_crypto_universe_filters(config)
    return {
        "broker": "bybit",
        "min_volume_24h_usd": flt.min_turnover_24h_usd,
        "max_spread_pct": round(flt.max_spread_pct, 6),
        "max_spread_note": "percent: 0.15 = 0.15% bid-ask; applies on live screening only",
        "min_last_price": flt.min_last_price,
        "limit": flt.limit,
        "category": flt.category,
        "quote_coin": flt.quote_coin,
        "min_funding_rate": flt.min_funding_rate,
        "max_funding_rate": flt.max_funding_rate,
        "min_open_interest_usd": flt.min_open_interest_usd,
        "min_lsr": flt.min_lsr,
        "max_lsr": flt.max_lsr,
        "min_rvol": flt.min_rvol,
        "min_atr_percent": flt.min_atr_percent,
        "max_atr_percent": flt.max_atr_percent,
        "lookback_days": flt.lookback_days,
    }


def _reason_key(reason: str) -> str:
    base = str(reason or "unknown").strip()
    if ":" in base:
        base = base.split(":", 1)[0]
    return base or "unknown"


def _format_reject_line(dr: Dict[str, Any], filters: Dict[str, Any]) -> str:
    ticker = str(dr.get("ticker") or "?")
    day = str(dr.get("trade_date") or "?")
    reason = _reason_key(str(dr.get("reason") or "unknown"))
    parts = [f"{day} | {ticker} | {reason}"]

    if reason == "volume_below_min" and dr.get("turnover24h") is not None:
        min_vol = filters.get("min_volume_24h_usd")
        vol = float(dr["turnover24h"])
        if min_vol is not None:
            parts.append(f"volume={vol:,.0f} < min={float(min_vol):,.0f}")
        else:
            parts.append(f"volume={vol:,.0f}")
    elif reason == "spread_above_max":
        spread_pct = dr.get("spreadPercent")
        max_pct = filters.get("max_spread_pct")
        if spread_pct is not None and max_pct is not None:
            parts.append(f"spread={_pct_str(spread_pct)} > max={_pct_str(max_pct)}")
        elif spread_pct is not None:
            parts.append(f"spread={_pct_str(spread_pct)}")
    elif reason == "price_below_min" and dr.get("lastPrice") is not None:
        min_price = filters.get("min_last_price")
        if min_price is not None and float(min_price) > 0:
            parts.append(f"price={dr['lastPrice']} < min={min_price}")
    else:
        if dr.get("turnover24h") is not None:
            parts.append(f"volume={float(dr['turnover24h']):,.0f}")
        if dr.get("spreadPercent") is not None:
            parts.append(f"spread={_pct_str(dr.get('spreadPercent'))}")
        if dr.get("dailyRangePercent") is not None:
            parts.append(f"daily_range={_pct_str(dr.get('dailyRangePercent'))}")
        if (
            dr.get("lastPrice") is not None
            and filters.get("min_last_price") is not None
            and float(filters["min_last_price"]) > 0
        ):
            parts.append(f"price={dr['lastPrice']}")

    if dr.get("avg_funding_rate") is not None:
        parts.append(f"funding={dr['avg_funding_rate']}")
    if dr.get("open_interest_usd") is not None:
        parts.append(f"oi_usd={dr['open_interest_usd']:,.0f}")
    if dr.get("lsr") is not None:
        parts.append(f"lsr={dr['lsr']}")
    if dr.get("rvol") is not None:
        parts.append(f"rvol={dr['rvol']}")
    if dr.get("atr_percent") is not None:
        parts.append(f"atr_pct={dr['atr_percent']}")
    payload = dr.get("payload")
    if isinstance(payload, dict) and payload.get("eval"):
        ev = payload.get("eval")
        if isinstance(ev, dict) and ev.get("reason"):
            parts.append(f"eval={ev.get('reason')}")
    return " | ".join(parts)


def build_universe_reject_summary(
    decisions_rows: List[Dict[str, Any]],
    *,
    filters: Dict[str, Any],
    day_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    sample_per_reason: int = 5,
) -> Dict[str, Any]:
    rejects = [dr for dr in decisions_rows if str(dr.get("result") or "").upper() == "REJECT"]
    accepts = [dr for dr in decisions_rows if str(dr.get("result") or "").upper() == "ACCEPT"]

    by_reason: Dict[str, int] = defaultdict(int)
    by_day: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"rejects": 0, "accepts": 0, "by_reason": defaultdict(int)}
    )
    samples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for dr in rejects:
        reason = _reason_key(str(dr.get("reason") or "unknown"))
        day = str(dr.get("trade_date") or "unknown")
        by_reason[reason] += 1
        by_day[day]["rejects"] += 1
        by_day[day]["by_reason"][reason] += 1
        if len(samples[reason]) < sample_per_reason:
            samples[reason].append(dr)

    for dr in accepts:
        day = str(dr.get("trade_date") or "unknown")
        by_day[day]["accepts"] += 1

    by_day_out: Dict[str, Any] = {}
    for day, st in sorted(by_day.items()):
        reasons = dict(st["by_reason"])
        top = sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:5]
        by_day_out[day] = {
            "rejects": int(st["rejects"]),
            "accepts": int(st["accepts"]),
            "by_reason": reasons,
            "top_rejects": [{"reason": k, "count": v} for k, v in top],
        }
        if day_stats and day in day_stats:
            by_day_out[day]["pipeline_stats"] = dict(day_stats[day])

    return {
        "totals": {
            "rejects": len(rejects),
            "accepts": len(accepts),
            "trade_days": len(by_day_out),
        },
        "filters": filters,
        "by_reason": dict(sorted(by_reason.items(), key=lambda x: x[1], reverse=True)),
        "by_day": by_day_out,
        "samples_by_reason": {k: v for k, v in samples.items()},
    }


def _resolve_run_dir(run_id: int) -> Path:
    session = _session_for(run_id)
    if session is not None:
        return session.run_dir
    return backtest_run_dir(run_id)


def emit_universe_reject_report(
    run_id: int,
    *,
    decisions_rows: List[Dict[str, Any]],
    config: Dict[str, Any],
    day_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    is_crypto: bool = False,
    sample_per_reason: int = 5,
    log_day_samples: int = 3,
) -> Optional[Path]:
    """Пишет universe_rejects.jsonl + universe_rejects_summary.json и краткий отчёт в backtest.log."""
    if not decisions_rows:
        return None

    run_dir = _resolve_run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    filters = _filters_snapshot(config, is_crypto=is_crypto)
    summary = build_universe_reject_summary(
        decisions_rows,
        filters=filters,
        day_stats=day_stats,
        sample_per_reason=sample_per_reason,
    )

    jsonl_path = run_dir / "universe_rejects.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for dr in decisions_rows:
            if str(dr.get("result") or "").upper() != "REJECT":
                continue
            fh.write(json.dumps(dr, ensure_ascii=False, default=str) + "\n")

    summary_path = run_dir / "universe_rejects_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    log_backtest_run_info("UNIVERSE | reject report: %s", str(run_dir), run_id=run_id)
    log_backtest_run_info("UNIVERSE | filters: %s", json.dumps(filters, ensure_ascii=False), run_id=run_id)
    log_backtest_run_info(
        "UNIVERSE | totals: rejects=%s accepts=%s days=%s",
        summary["totals"]["rejects"],
        summary["totals"]["accepts"],
        summary["totals"]["trade_days"],
        run_id=run_id,
    )
    top_global = list(summary.get("by_reason", {}).items())[:8]
    if top_global:
        log_backtest_run_info(
            "UNIVERSE | top_rejects: %s",
            "; ".join(f"{k} x{v}" for k, v in top_global),
            run_id=run_id,
        )

    for day, dst in summary.get("by_day", {}).items():
        top_day = dst.get("top_rejects") or []
        top_txt = "; ".join(f"{x['reason']} x{x['count']}" for x in top_day[:5]) or "—"
        log_backtest_run_info(
            "UNIVERSE | day=%s rejected=%s accepted=%s | %s",
            day,
            dst.get("rejects", 0),
            dst.get("accepts", 0),
            top_txt,
            run_id=run_id,
        )
        day_rejects = [
            dr
            for dr in decisions_rows
            if str(dr.get("result") or "").upper() == "REJECT" and str(dr.get("trade_date") or "") == day
        ]
        for dr in day_rejects[:log_day_samples]:
            log_backtest_run_info("UNIVERSE |   %s", _format_reject_line(dr, filters), run_id=run_id)
        if len(day_rejects) > log_day_samples:
            log_backtest_run_info(
                "UNIVERSE |   ... ещё %s отклонений за %s (см. universe_rejects.jsonl)",
                len(day_rejects) - log_day_samples,
                day,
                run_id=run_id,
            )

    for reason, samples in summary.get("samples_by_reason", {}).items():
        log_backtest_run_info("UNIVERSE | examples reason=%s:", reason, run_id=run_id)
        for dr in samples:
            log_backtest_run_info("UNIVERSE |   %s", _format_reject_line(dr, filters), run_id=run_id)

    log_backtest_run_info(
        "UNIVERSE | full detail: %s (%s lines)",
        jsonl_path.name,
        summary["totals"]["rejects"],
        run_id=run_id,
    )
    return run_dir
