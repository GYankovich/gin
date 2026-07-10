"""Backtest persist phase (DB writes after simulation). Shared by worker and reconcile."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.robots.trading.backtest.types import BacktestResult

logger = logging.getLogger(__name__)

ProgressFlushFn = Callable[..., None]
DtDateUtcFn = Callable[[datetime], Any]


def execute_backtest_persist_phase(
    *,
    flush_progress: ProgressFlushFn,
    dt_date_utc: DtDateUtcFn,
    db: Session,
    progress_bind: Any,
    run_id: int,
    run_started_at: datetime,
    td_total: int,
    skip_heavy_persist: bool,
    bt_run_id: Optional[int],
    res: BacktestResult,
    slippage_pct: float,
    decisions_rows: List[Dict[str, Any]],
    is_crypto_backtest: bool,
    config: Dict[str, Any],
    result: Dict[str, Any],
    robot_pk: Optional[int],
    requested_from_utc: datetime,
    requested_to_utc: datetime,
    pipeline_user_cancelled: bool,
) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
    """
    Write backtest artifacts to DB after simulation.

    Returns (backtest_log_status, backtest_log_summary, backtest_log_error).
    """
    from app.modules.recommendations.backtest_analytics import (
        bybit_metrics,
        exit_reason_metrics,
        general_metrics,
        moex_metrics,
        universe_metrics,
    )
    from app.modules.robots.service import (
        _bulk_persist_backtest_rows,
        _bulk_persist_daily_universe,
        _compute_persist_phase_units_total,
        is_history_backtest_cancelled,
    )
    from app.modules.robots.trading.backtest.metrics import BacktestMetricsCalculator
    from app.modules.robots.trading.backtest.persistence import (
        BacktestPersistence,
        BacktestPersistPayload,
    )
    from app.modules.robots.trading.backtest.run_file_logger import log_backtest_run_info

    persist_units_total = _compute_persist_phase_units_total(
        decisions_rows=decisions_rows,
        bt_run_id=bt_run_id,
    )
    if bt_run_id and not skip_heavy_persist:
        sig_n = len(getattr(res, "signals", None) or [])
        tr_n = len(getattr(res, "trades", None) or [])
        persist_units_total += max(1, (sig_n + 499) // 500)
        persist_units_total += max(1, (tr_n + 499) // 500)
        persist_units_total += 2
    persist_units_done = 0

    def _persist_progress_report() -> None:
        flush_progress(
            progress_bind,
            run_id,
            "persisting",
            phase_units_done=min(persist_units_done, persist_units_total),
            phase_units_total=persist_units_total,
            trade_dates_total=td_total,
            started_at=run_started_at,
        )

    def _persist_progress_advance() -> None:
        nonlocal persist_units_done
        persist_units_done += 1
        _persist_progress_report()

    if not skip_heavy_persist:
        _persist_progress_report()
        db.execute(
            text(
                f"UPDATE {settings.DB_SCHEMA}.backtest_runs SET run_phase='persisting' WHERE id=:rid"
            ),
            {"rid": run_id},
        )
        db.commit()

    if not skip_heavy_persist:
        _bulk_persist_backtest_rows(
            db,
            run_id=run_id,
            res=res,
            decisions_rows=decisions_rows,
            slippage_pct=slippage_pct,
            on_core_done=_persist_progress_advance,
            on_decision_chunk_done=_persist_progress_advance,
        )
    if bt_run_id and not skip_heavy_persist:
        try:
            _bulk_persist_daily_universe(
                db,
                bt_run_id=bt_run_id,
                decisions_rows=decisions_rows,
                on_chunk_done=_persist_progress_advance,
            )
        except Exception as ex:
            logger.warning("bulk persist backtest_daily_universe failed bt_run_id=%s: %s", bt_run_id, ex)
            db.rollback()
    if not skip_heavy_persist:
        db.commit()

    calendar_days_cnt = (
        dt_date_utc(requested_to_utc) - dt_date_utc(requested_from_utc)
    ).days + 1
    m = BacktestMetricsCalculator.calculate(
        res=res,
        broker_type="bybit" if is_crypto_backtest else "tinvest",
        calendar_days_cnt=calendar_days_cnt,
    )
    winning = list(m["winning"])
    closed = list(m["closed"])
    avg_pnl = m["avg_pnl"]
    win_rate = m["win_rate"]
    gross_profit_val = float(m["gross_profit_val"])
    gross_loss_val = float(m["gross_loss_val"])
    net_profit_val = float(m["net_profit_val"])
    total_commission_val = float(m["total_commission_val"])
    profit_factor_val = m["profit_factor_val"]
    avg_win_val = m["avg_win_val"]
    avg_loss_val = m["avg_loss_val"]
    equity_by_day = dict(m["equity_by_day"])
    trading_days_cnt = int(m["trading_days_cnt"] or 0)
    annualized_return_val = m["annualized_return_val"]
    volatility_annual_val = m["volatility_annual_val"]
    rec_analytics: Dict[str, float] = {}
    for k, v in exit_reason_metrics(res.trades or [], res.signals or []).items():
        if v is not None:
            rec_analytics[k] = float(v)
    for k, v in universe_metrics(result, res.trades or []).items():
        if v is not None:
            rec_analytics[k] = float(v)
    if not is_crypto_backtest:
        costs_cfg = config.get("costs") if isinstance(config.get("costs"), dict) else {}
        risk_cfg = config.get("risk") if isinstance(config.get("risk"), dict) else {}
        for k, v in moex_metrics(
            result,
            res.trades or [],
            risk_config=risk_cfg,
            costs_config=costs_cfg,
            decisions_rows=decisions_rows,
        ).items():
            if v is not None:
                rec_analytics[k] = float(v)
    else:
        for k, v in bybit_metrics(
            result,
            res.trades or [],
            config=config,
            slippage_pct=slippage_pct,
        ).items():
            if v is not None:
                rec_analytics[k] = float(v)
    broker_type_str = "bybit" if is_crypto_backtest else "tinvest"
    for k, v in general_metrics(
        result,
        res.trades or [],
        getattr(res, "signals", None) or [],
        broker_type=broker_type_str,
        volatility_annual_pct=volatility_annual_val,
    ).items():
        if v is not None:
            rec_analytics[k] = float(v)
    result["history_stats"] = {
        **dict(result.get("history_stats") or {}),
        "trading_days_with_equity": trading_days_cnt,
        "calendar_days": int(m.get("calendar_days_cnt") or calendar_days_cnt),
        "annualization_days": int(m.get("annualization_days") or 252),
        "annualized_return_percent": annualized_return_val,
        **rec_analytics,
    }
    sharpe_val = m["sharpe_val"]
    sortino_val = m["sortino_val"]
    calmar_val = m["calmar_val"]
    max_dd_duration = int(m["max_dd_duration"] or 0)
    if bt_run_id and not skip_heavy_persist:
        persist_payload = BacktestPersistPayload(
            equity_by_day=equity_by_day,
            trading_days_cnt=trading_days_cnt,
            win_rate=win_rate,
            annualized_return_val=annualized_return_val,
            max_dd_duration=max_dd_duration,
            sharpe_val=sharpe_val,
            sortino_val=sortino_val,
            calmar_val=calmar_val,
            volatility_annual_val=volatility_annual_val,
            gross_profit_val=gross_profit_val,
            gross_loss_val=gross_loss_val,
            total_commission_val=total_commission_val,
            net_profit_val=net_profit_val,
            profit_factor_val=profit_factor_val,
            avg_pnl=avg_pnl,
            avg_win_val=avg_win_val,
            avg_loss_val=avg_loss_val,
            winning_count=len(winning),
            closed_count=len(closed),
            start_date=dt_date_utc(requested_from_utc),
            end_date=dt_date_utc(requested_to_utc),
        )
        BacktestPersistence(db).persist_run_details(
            bt_run_id=bt_run_id,
            res=res,
            slippage_pct=slippage_pct,
            payload=persist_payload,
            on_progress=_persist_progress_advance,
        )
    if not skip_heavy_persist:
        persist_units_done = persist_units_total
        _persist_progress_report()

    db.execute(
        text(f"""
            INSERT INTO {settings.DB_SCHEMA}.backtest_metrics
            (run_id, total_return_percent, max_drawdown_percent, sharpe_ratio, trades_total, win_rate_percent, avg_pnl_per_trade, final_equity, payload)
            VALUES (:run_id, :total_return_percent, :max_drawdown_percent, NULL, :trades_total, :win_rate_percent, :avg_pnl_per_trade, :final_equity, CAST(:payload AS jsonb))
            ON CONFLICT (run_id) DO UPDATE SET
                total_return_percent = EXCLUDED.total_return_percent,
                max_drawdown_percent = EXCLUDED.max_drawdown_percent,
                trades_total = EXCLUDED.trades_total,
                win_rate_percent = EXCLUDED.win_rate_percent,
                avg_pnl_per_trade = EXCLUDED.avg_pnl_per_trade,
                final_equity = EXCLUDED.final_equity,
                payload = EXCLUDED.payload
        """),
        {
            "run_id": run_id,
            "total_return_percent": res.total_return_percent,
            "max_drawdown_percent": res.max_drawdown_percent,
            "trades_total": len(res.trades),
            "win_rate_percent": win_rate,
            "avg_pnl_per_trade": avg_pnl,
            "final_equity": res.final_equity,
            "payload": json.dumps(result, ensure_ascii=False),
        },
    )
    db.commit()

    sim_or_pipeline_cancelled = (
        bool(getattr(res, "cancelled", False))
        or pipeline_user_cancelled
        or is_history_backtest_cancelled(run_id)
    )
    if not sim_or_pipeline_cancelled:
        backtest_log_status = "SUCCESS"
    else:
        backtest_log_status = "CANCELLED"
    backtest_log_summary = {
        "total_return_percent": res.total_return_percent,
        "max_drawdown_percent": res.max_drawdown_percent,
        "trades_total": len(res.trades),
        "final_equity": res.final_equity,
        "cancelled": sim_or_pipeline_cancelled,
    }
    log_backtest_run_info(
        "RESULT total_return=%.4f%% trades=%s final_equity=%s",
        float(res.total_return_percent or 0),
        len(res.trades),
        res.final_equity,
    )
    if not sim_or_pipeline_cancelled:
        db.execute(
            text(f"""
            UPDATE {settings.DB_SCHEMA}.backtest_runs
            SET status='SUCCESS',
                finished_at=:finished_at,
                progress_percent=100,
                eta_seconds=0,
                eta_confidence='high',
                run_phase='completed',
                metrics_summary=CAST(:summary AS jsonb)
            WHERE id=:run_id
        """),
            {
                "run_id": run_id,
                "finished_at": datetime.now(timezone.utc),
                "summary": json.dumps({
                    "total_return_percent": res.total_return_percent,
                    "max_drawdown_percent": res.max_drawdown_percent,
                    "trades_total": len(res.trades),
                    "final_equity": res.final_equity,
                }, ensure_ascii=False),
            },
        )
    else:
        cancel_phase = "cancelled_simulation" if bool(getattr(res, "cancelled", False)) else "cancelled"
        try:
            db.execute(
                text(f"""
                UPDATE {settings.DB_SCHEMA}.backtest_runs
                SET status = 'CANCELLED',
                    partial_result = true,
                    run_phase = :rp,
                    finished_at = COALESCE(finished_at, :finished_at),
                    metrics_summary = CAST(:summary AS jsonb)
                WHERE id = :run_id
            """),
                {
                    "run_id": run_id,
                    "rp": cancel_phase,
                    "finished_at": datetime.now(timezone.utc),
                    "summary": json.dumps({
                        "total_return_percent": res.total_return_percent,
                        "max_drawdown_percent": res.max_drawdown_percent,
                        "trades_total": len(res.trades),
                        "final_equity": res.final_equity,
                        "cancelled": True,
                    }, ensure_ascii=False),
                },
            )
        except Exception:
            db.rollback()
    if robot_pk is not None:
        save_sql = f"""
            INSERT INTO {settings.DB_SCHEMA}.robot_backtest_runs
            (robot_id, requested_from, requested_to, initial_capital, final_equity, total_return_percent, max_drawdown_percent, result_payload, created_at)
            VALUES
            (:robot_id, :requested_from, :requested_to, :initial_capital, :final_equity, :total_return_percent, :max_drawdown_percent, CAST(:result_payload AS jsonb), :created_at)
        """
        db.execute(
            text(save_sql),
            {
                "robot_id": robot_pk,
                "requested_from": requested_from_utc,
                "requested_to": requested_to_utc,
                "initial_capital": res.initial_capital,
                "final_equity": res.final_equity,
                "total_return_percent": res.total_return_percent,
                "max_drawdown_percent": res.max_drawdown_percent,
                "result_payload": json.dumps(result, ensure_ascii=False, default=str),
                "created_at": datetime.now(timezone.utc),
            },
        )
    db.commit()
    return backtest_log_status, backtest_log_summary, None
