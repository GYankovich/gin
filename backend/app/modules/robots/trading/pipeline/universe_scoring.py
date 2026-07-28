"""Per-day universe scoring for history backtest — та же логика, что live DMS pipeline."""



from __future__ import annotations



import asyncio

import json

import logging

from contextlib import asynccontextmanager

from dataclasses import dataclass, field

from datetime import date

from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol



from sqlalchemy import text

from sqlalchemy.orm import Session



from app.core.config import settings

from app.modules.corporate_actions.dividend_calendar_service import DividendCalendarService

from app.modules.dms.service import dms_service

from app.modules.robots.backtest_progress import touch_backtest_progress_runtime

from app.modules.robots.universe import universe_filter_snapshot_row
from app.modules.robots.trading.pipeline.historical_liquidity import (
    avg_daily_value_rub_from_candles,
    volume_lookback_days,
)



logger = logging.getLogger(__name__)



# Подшаги на торговый день: start → snapshot → rows → filter → final/ATR → done

SCORING_PROGRESS_SUBSTEPS = 5

_HEARTBEAT_INTERVAL_SEC = 20.0





class ProgressFlush(Protocol):

    def __call__(self, phase_units_done: int, *, current_trade_date: date, trade_dates_remaining: int) -> None: ...





@dataclass

class UniverseScoringResult:

    allowed_figis_by_date: Dict[str, List[str]] = field(default_factory=dict)

    decisions_rows: List[Dict[str, Any]] = field(default_factory=list)

    day_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)

    processed_days: int = 0

    skipped_fetch_days: int = 0

    skipped_empty_days: int = 0

    missing_history_days: List[str] = field(default_factory=list)

    last_history_error: Optional[str] = None

    selected_tickers: List[str] = field(default_factory=list)

    cancelled: bool = False





@asynccontextmanager

async def _scoring_heartbeat(run_id: Optional[int]):

    """Периодический touch, чтобы scoring-timeout не срабатывал на тяжёлом дне."""

    if run_id is None:

        yield

        return

    stop = asyncio.Event()



    async def _loop() -> None:

        while not stop.is_set():

            touch_backtest_progress_runtime(run_id)

            try:

                await asyncio.wait_for(stop.wait(), timeout=_HEARTBEAT_INTERVAL_SEC)

            except asyncio.TimeoutError:

                continue



    task = asyncio.create_task(_loop())

    try:

        yield

    finally:

        stop.set()

        task.cancel()

        try:

            await task

        except asyncio.CancelledError:

            pass





async def run_history_universe_scoring(

    *,

    db: Session,

    robot_service: Any,

    trade_dates: List[date],

    board: str,

    config: Dict[str, Any],

    pipeline_filters: List[Dict[str, Any]],

    fast_pipeline_filters: List[Dict[str, Any]],

    pipeline_mode: str,

    allowed_tickers_whitelist: Optional[set[str]],

    div_policy: Any,

    user_id: int,

    run_id: int,

    ensure_snapshot: Callable[..., Awaitable[Optional[int]]],

    is_cancelled: Callable[[], bool],

    flush_progress: Optional[ProgressFlush] = None,

) -> UniverseScoringResult:

    """Отбор бумаг по дням: БД snapshot → pipeline fast/final → ATR из кэша → дивиденды."""

    out = UniverseScoringResult()

    td_total = len(trade_dates)

    board_issuesize_map: Dict[str, float] = await robot_service._fetch_board_issuesize_map(board=board)

    div_svc = DividendCalendarService(db)

    div_ex_index = (

        div_svc.preload_exclusion_index(

            sorted(board_issuesize_map.keys()),

            trade_dates[0],

            trade_dates[-1],

        )

        if trade_dates

        else {}

    )



    async with _scoring_heartbeat(run_id):

        for day_ord, d in enumerate(trade_dates):

            await asyncio.sleep(0)

            rem_day = max(0, td_total - day_ord - 1)



            def _flush(substep: int) -> None:

                if flush_progress is None:

                    return

                flush_progress(

                    day_ord * SCORING_PROGRESS_SUBSTEPS + substep,

                    current_trade_date=d,

                    trade_dates_remaining=rem_day,

                )



            def _touch() -> None:

                touch_backtest_progress_runtime(run_id)



            if is_cancelled():

                out.cancelled = True

                break



            _flush(0)

            _touch()

            day_selected: set[str] = set()

            day_rows: List[Dict[str, Any]] = []

            fast_passed: List[Dict[str, Any]] = []



            try:

                snapshot_id = await ensure_snapshot(db, day=d, board=board, user_id=user_id, run_id=run_id)

            except Exception as e:

                logger.warning("history snapshot day skipped day=%s err=%s", d.isoformat(), e)

                out.last_history_error = str(e)

                out.skipped_fetch_days += 1

                out.missing_history_days.append(d.isoformat())

                _flush(SCORING_PROGRESS_SUBSTEPS - 1)

                continue



            _flush(1)

            _touch()



            if not snapshot_id:

                out.skipped_empty_days += 1

                out.missing_history_days.append(d.isoformat())

                _flush(SCORING_PROGRESS_SUBSTEPS - 1)

                continue



            if is_cancelled():

                out.cancelled = True

                break



            out.processed_days += 1

            rows = db.execute(

                text(f"""

                    SELECT ticker, last_price, open_price, high_price, low_price, prev_price, value_today,

                           volume_lots, bid, ask, spread, security_status, trading_status, num_trades,

                           issue_size, min_step, prev_legal_close_price, isin, lot_size, close_price,

                           securities_payload

                    FROM {settings.DB_SCHEMA}.market_snapshot_data_history

                    WHERE snapshot_id = :snapshot_id

                """),

                {"snapshot_id": snapshot_id},

            ).mappings().all()



            if not rows:

                _flush(SCORING_PROGRESS_SUBSTEPS - 1)

                continue



            _flush(2)

            _touch()

            day_key = d.isoformat()

            out.day_stats[day_key] = {"rows_total": len(rows), "fast_passed": 0, "final_passed": 0}



            for ri, r in enumerate(rows):

                if ri > 0 and ri % 40 == 0:

                    _touch()

                    await asyncio.sleep(0)

                if ri > 0 and ri % 120 == 0:

                    _flush(2)

                if ri % 40 == 0 and is_cancelled():

                    out.cancelled = True

                    break



                row = dict(r)

                ticker = str(row.get("ticker") or "").strip().upper()

                if not universe_filter_snapshot_row(row, config):

                    continue

                if board_issuesize_map and ticker:

                    ex = row.get("issue_size")

                    if ex is None or (isinstance(ex, (int, float)) and float(ex) <= 0):

                        sz = board_issuesize_map.get(ticker)

                        if sz is not None and sz > 0:

                            row["issue_size"] = float(sz)

                lp = robot_service._safe_float_opt(row.get("last_price"))

                pp = robot_service._safe_float_opt(row.get("prev_price"))

                if lp and pp and abs(lp - pp) < 1e-5:

                    try:

                        raw_pl = row.get("securities_payload")

                        if isinstance(raw_pl, str):

                            raw_pl = json.loads(raw_pl)

                        if isinstance(raw_pl, dict):

                            trend = robot_service._safe_float_opt(raw_pl.get("TRENDCLSPR"))

                            if trend is not None and lp > 0:

                                denom = 1.0 + trend / 100.0

                                if abs(denom) > 1e-12:

                                    row["prev_price"] = float(lp / denom)

                    except Exception:

                        pass

                if ticker:
                    lookback = volume_lookback_days(config)
                    avg_val = avg_daily_value_rub_from_candles(
                        db,
                        ticker=ticker,
                        as_of_date=d,
                        lookback_days=lookback,
                        market="moex",
                    )
                    if avg_val is not None:
                        row["historical_avg_volume_rub"] = avg_val
                        row["value_today"] = avg_val

                day_rows.append(row)



                eval_res = dms_service._evaluate_pipeline_row(

                    row,

                    fast_pipeline_filters,

                    pipeline_mode,

                    allow_missing_spread=True,

                    allowed_figis=allowed_tickers_whitelist,

                )

                if bool(eval_res.get("accepted")) and ticker:

                    fast_passed.append(row)

                    out.day_stats[day_key]["fast_passed"] += 1

                else:

                    out.decisions_rows.append({

                        "trade_date": day_key,

                        "ticker": ticker,

                        "result": "REJECT",

                        "reason": eval_res.get("reason") or "fast_filter_reject",

                        "payload": {"stage": "fast", "eval": eval_res},

                    })



            if out.cancelled:

                break



            _flush(3)

            _touch()

            if fast_passed:

                atr_map, _ = await dms_service._load_atr_percent_map(

                    db=db,

                    board=board,

                    rows=fast_passed,

                    filters=pipeline_filters,

                    as_of_date=d,

                    fetch_missing_candles=False,

                    user_id=user_id,

                )

                _touch()

                for fi, fr in enumerate(fast_passed):

                    if fi > 0 and fi % 25 == 0:

                        _touch()

                        await asyncio.sleep(0)

                    if is_cancelled():

                        out.cancelled = True

                        break

                    tk = str(fr.get("ticker") or "").upper()

                    if not tk:

                        continue

                    enriched = dict(fr)

                    if tk in atr_map:

                        enriched["atr_percent"] = atr_map[tk]

                    final_eval = dms_service._evaluate_pipeline_row(

                        enriched,

                        pipeline_filters,

                        pipeline_mode,

                        allow_missing_spread=True,

                        allowed_figis=allowed_tickers_whitelist,

                    )

                    if bool(final_eval.get("accepted")):

                        dd_reason = div_svc.exclusion_reason_for_day_cached(

                            ticker=tk,

                            trade_date=d,

                            policy=div_policy,

                            ex_dates=div_ex_index.get(tk),

                        )

                        if dd_reason:

                            out.decisions_rows.append({

                                "trade_date": day_key,

                                "ticker": tk,

                                "result": "REJECT",

                                "reason": dd_reason,

                                "payload": {"stage": "dividend_calendar", "policy": div_policy.__dict__},

                            })

                            continue

                        out.selected_tickers.append(tk)

                        day_selected.add(tk)

                        out.day_stats[day_key]["final_passed"] += 1

                        out.decisions_rows.append({

                            "trade_date": day_key,

                            "ticker": tk,

                            "result": "ACCEPT",

                            "reason": None,

                            "payload": {"stage": "final", "eval": final_eval},

                        })

                    else:

                        out.decisions_rows.append({

                            "trade_date": day_key,

                            "ticker": tk,

                            "result": "REJECT",

                            "reason": final_eval.get("reason") or "final_filter_reject",

                            "payload": {"stage": "final", "eval": final_eval},

                        })



            out.allowed_figis_by_date[day_key] = sorted(day_selected)

            _flush(SCORING_PROGRESS_SUBSTEPS - 1)

            if out.cancelled:

                break



    return out





__all__ = ["run_history_universe_scoring", "UniverseScoringResult", "SCORING_PROGRESS_SUBSTEPS"]

