"""Background prefetch of ByBit D1 candles and funding before crypto universe scoring."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

_PREFETCH_PHASE = "prefetching_crypto_market"
_LOG_EVERY_UNITS = 10


def _parse_trade_dates(raw: Iterable[Any]) -> List[date]:
    out: List[date] = []
    for item in raw or []:
        if isinstance(item, date):
            out.append(item)
            continue
        s = str(item or "").strip()
        if not s:
            continue
        out.append(date.fromisoformat(s[:10]))
    return out


def _cancel_checker(run_id: int) -> Callable[[], bool]:
    """Isolated DB session — safe while main session is busy with prefetch writes."""

    def _is_cancelled() -> bool:
        from app.core.database import SessionLocal

        cdb = SessionLocal()
        try:
            row = cdb.execute(
                text(
                    f"""
                    SELECT cancel_requested
                    FROM backtest_runs
                    WHERE id = :rid
                    LIMIT 1
                    """
                ),
                {"rid": int(run_id)},
            ).mappings().first()
            return bool((row or {}).get("cancel_requested"))
        finally:
            cdb.close()

    return _is_cancelled


async def estimate_crypto_prefetch_units(
    db: Session,
    *,
    trade_dates: Iterable[date],
    config: dict[str, Any],
    allowed_tickers_whitelist: Optional[Set[str]] = None,
) -> int:
    """Rough progress denominator: symbols × (D1 step + funding step)."""
    from app.modules.robots.trading.data.providers.bybit_market import (
        resolve_crypto_screening_symbols,
    )

    symbols = await resolve_crypto_screening_symbols(
        db,
        config=config,
        allowed_tickers_whitelist=allowed_tickers_whitelist,
        prefer_live_universe=True,
    )
    if not symbols:
        return 1
    bybit = config.get("bybit") if isinstance(config.get("bybit"), dict) else {}
    instrument_category = str(bybit.get("instrument_category") or "linear").strip().lower() or "linear"
    steps = 1 if instrument_category == "spot" else 2
    return max(1, len(symbols) * steps)


async def schedule_crypto_screening_prefetch(
    db: Session,
    *,
    run_id: int,
    user_id: int,
    body: Dict[str, Any],
    trade_dates: Iterable[date],
    config: dict[str, Any],
    allowed_tickers_whitelist: Optional[Set[str]] = None,
    progress_bind: Any,
    run_started_at: Optional[datetime] = None,
) -> bool:
    """
    Enqueue lane=heavy job ``crypto_screening_prefetch``.

    Returns True when the history-backtest worker must exit and wait for prefetch.
    """
    from app.core.background_jobs.repository import enqueue_background_job
    from app.core.background_jobs.worker import LANE_HEAVY
    from app.modules.robots.backtest_progress import persist_backtest_progress

    dates = list(trade_dates)
    td_total = len(dates)
    units_total = await estimate_crypto_prefetch_units(
        db,
        trade_dates=dates,
        config=config,
        allowed_tickers_whitelist=allowed_tickers_whitelist,
    )
    dates_iso = [d.isoformat() for d in dates]
    job_id = enqueue_background_job(
        db,
        lane=LANE_HEAVY,
        job_type="crypto_screening_prefetch",
        payload={
            "run_id": int(run_id),
            "user_id": int(user_id),
            "body": dict(body or {}),
            "trade_dates": dates_iso,
        },
        idempotency_key=f"crypto_screening_prefetch:{int(run_id)}",
    )
    if job_id is None:
        logger.info(
            "crypto_screening_prefetch already queued/running run_id=%s",
            run_id,
        )
        return True

    db.execute(
        text(
            f"""
            UPDATE backtest_runs
            SET run_phase = :phase,
                phase_units_done = 0,
                phase_units_total = :units,
                trade_dates_total = :td,
                trade_dates_remaining = :td
            WHERE id = :rid
              AND COALESCE(cancel_requested, false) = false
            """
        ),
        {
            "phase": _PREFETCH_PHASE,
            "units": int(units_total),
            "td": int(td_total),
            "rid": int(run_id),
        },
    )
    db.commit()

    bind = progress_bind or db.get_bind()
    persist_backtest_progress(
        bind,
        int(run_id),
        run_phase=_PREFETCH_PHASE,
        phase_units_done=0,
        phase_units_total=int(units_total),
        trade_dates_total=int(td_total) if td_total > 0 else None,
        trade_dates_remaining=int(td_total) if td_total > 0 else None,
        started_at=run_started_at,
    )
    logger.info(
        "scheduled crypto_screening_prefetch run_id=%s job_id=%s units=%s",
        run_id,
        job_id,
        units_total,
    )
    return True


def _progress_reporter(
    *,
    run_id: int,
    progress_bind: Any,
    run_started_at: Optional[datetime],
    units_total: int,
    trade_dates_total: int,
) -> Callable[[int, int], None]:
    from app.modules.robots.backtest_progress import persist_backtest_progress
    from app.modules.robots.trading.backtest.run_file_logger import log_backtest_run_info

    last_logged = 0

    def _flush(done: int, total: int) -> None:
        nonlocal last_logged
        ut = max(1, int(units_total), int(total))
        ud = min(int(done), ut)
        persist_backtest_progress(
            progress_bind,
            run_id,
            run_phase=_PREFETCH_PHASE,
            phase_units_done=ud,
            phase_units_total=ut,
            trade_dates_total=trade_dates_total if trade_dates_total > 0 else None,
            trade_dates_remaining=trade_dates_total if trade_dates_total > 0 else None,
            started_at=run_started_at,
        )
        if ud == 1 or ud >= ut or ud - last_logged >= _LOG_EVERY_UNITS:
            try:
                log_backtest_run_info(
                    "PREFETCH | progress %s/%s (%.1f%%)",
                    ud,
                    ut,
                    100.0 * ud / ut,
                )
            except Exception:
                pass
            last_logged = ud

    return _flush


async def run_crypto_screening_prefetch(payload: Dict[str, Any]) -> None:
    """Worker handler: D1 + funding prefetch, then enqueue history_backtest continuation."""
    from app.core.database import SessionLocal
    from app.modules.robots.trading.backtest.run_file_logger import (
        close_backtest_run_log,
        log_backtest_run_error,
        log_backtest_run_exception,
        log_backtest_run_info,
        ensure_backtest_run_log,
    )
    from app.modules.robots.trading.data.providers.bybit_market import (
        ensure_crypto_screening_d1_candles,
        ensure_crypto_screening_funding_history,
    )

    run_id = int(payload["run_id"])
    user_id = int(payload["user_id"])
    body = dict(payload.get("body") or {})
    trade_dates = _parse_trade_dates(payload.get("trade_dates") or [])
    trade_dates_total = len(trade_dates)

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                f"""
                SELECT status, cancel_requested, config_snapshot, started_at
                FROM backtest_runs
                WHERE id = :rid AND user_id = :uid
                LIMIT 1
                """
            ),
            {"rid": run_id, "uid": user_id},
        ).mappings().first()
        if not row:
            raise RuntimeError(f"backtest run {run_id} not found")
        if bool(row.get("cancel_requested")):
            logger.info("crypto_screening_prefetch skipped (cancel) run_id=%s", run_id)
            return
        st = str(row.get("status") or "").upper()
        if st in ("SUCCESS", "FAILED", "CANCELLED"):
            logger.info("crypto_screening_prefetch skipped (status=%s) run_id=%s", st, run_id)
            return

        snap = row.get("config_snapshot")
        if isinstance(snap, dict):
            config = dict(snap)
        elif isinstance(snap, str):
            import json

            try:
                config = dict(json.loads(snap))
            except json.JSONDecodeError:
                config = {}
        else:
            config = dict(body.get("config") or {})

        run_started_at = row.get("started_at")
        if run_started_at is not None and getattr(run_started_at, "tzinfo", None) is None:
            run_started_at = run_started_at.replace(tzinfo=timezone.utc)

        try:
            ensure_backtest_run_log(
                run_id,
                started_at=run_started_at,
                meta={"run_id": run_id, "phase": _PREFETCH_PHASE, "deferred": True},
            )
            units_est = await estimate_crypto_prefetch_units(
                db, trade_dates=trade_dates, config=config,
            )
            from app.modules.robots.trading.backtest.backtest_narrative_log import narrative_section

            narrative_section("Подготовка данных для crypto-скрининга", run_id=run_id)
            log_backtest_run_info(
                "PREFETCH | background crypto_screening_prefetch started units_est=%s trade_dates=%s",
                units_est,
                trade_dates_total,
            )
        except Exception as log_ex:
            logger.warning("prefetch log open failed run_id=%s: %s", run_id, log_ex)

        units_total = await estimate_crypto_prefetch_units(db, trade_dates=trade_dates, config=config)
        progress_bind = db.get_bind()
        flush = _progress_reporter(
            run_id=run_id,
            progress_bind=progress_bind,
            run_started_at=run_started_at,
            units_total=units_total,
            trade_dates_total=trade_dates_total,
        )
        is_cancelled = _cancel_checker(run_id)

        from app.modules.robots.trading.data.providers.bybit_market import (
            resolve_crypto_screening_symbols,
            screening_d1_prefetch_range,
        )
        from app.modules.robots.trading.backtest.backtest_narrative_log import (
            backtest_narrative,
            format_candle_prefetch_result,
            format_funding_prefetch_result,
            format_symbol_list,
            narrative_result,
            narrative_step,
            narrative_sub,
        )

        with backtest_narrative(run_id):
            narrative_step("Получение списка perpetual-контрактов USDT на ByBit")
            screening_symbols = await resolve_crypto_screening_symbols(
                db,
                config=config,
                prefer_live_universe=True,
                user_id=user_id,
                run_id=run_id,
            )
            if not screening_symbols:
                narrative_result("Не удалось получить список инструментов ByBit")
                raise RuntimeError("crypto_screening_prefetch: no symbols from ByBit instruments API")
            narrative_result(
                f"Пул для скрининга: {len(screening_symbols)} символов — "
                f"{format_symbol_list(screening_symbols)}"
            )

            from_date, till_date = screening_d1_prefetch_range(trade_dates, config)
            narrative_step("Проверка и догрузка дневных свечей (D1) в candles_cache")
            narrative_sub(
                f"Символов в пуле: {len(screening_symbols)}; "
                f"диапазон prefetch: {from_date.isoformat()}..{till_date.isoformat()} "
                f"(lookback для ATR/объёма + торговые дни)"
            )
            d1_stats = await ensure_crypto_screening_d1_candles(
                db,
                trade_dates=trade_dates,
                config=config,
                symbols=screening_symbols,
                user_id=user_id,
                run_id=run_id,
                prefer_live_universe=True,
                is_cancelled=is_cancelled,
                progress_callback=lambda done, total: flush(done, max(units_total, total)),
            )
            narrative_result(format_candle_prefetch_result(d1_stats))
            log_backtest_run_info("PREFETCH | D1 %s", d1_stats.summary())
            if d1_stats.api_errors:
                log_backtest_run_error(
                    "PREFETCH | D1 api_errors=%s last=%s",
                    d1_stats.api_errors,
                    d1_stats.last_api_error,
                )
            if d1_stats.cancelled or is_cancelled():
                logger.info("crypto_screening_prefetch cancelled during D1 run_id=%s", run_id)
                return

            bybit = config.get("bybit") if isinstance(config.get("bybit"), dict) else {}
            instrument_category = str(bybit.get("instrument_category") or "linear").strip().lower() or "linear"
            symbol_count = max(1, d1_stats.total_tickers or 1)
            if instrument_category != "spot":
                narrative_step("Проверка и догрузка истории funding rate в БД")
                narrative_sub(
                    f"Категория {instrument_category}; символов {len(screening_symbols)}; "
                    f"торговые дни: {trade_dates_total}"
                )
                funding_offset = symbol_count

                def _funding_progress(done: int, total: int) -> None:
                    flush(funding_offset + done, max(units_total, funding_offset + total))

                funding_stats = await ensure_crypto_screening_funding_history(
                    db,
                    trade_dates=trade_dates,
                    config=config,
                    symbols=screening_symbols,
                    user_id=user_id,
                    run_id=run_id,
                    prefer_live_universe=True,
                    is_cancelled=is_cancelled,
                    progress_callback=_funding_progress,
                )
                narrative_result(format_funding_prefetch_result(funding_stats))
                log_backtest_run_info("PREFETCH | funding %s", funding_stats.summary())
                if funding_stats.api_errors:
                    log_backtest_run_error(
                        "PREFETCH | funding api_errors=%s last=%s",
                        funding_stats.api_errors,
                        funding_stats.last_api_error,
                    )
                if funding_stats.cancelled or is_cancelled():
                    logger.info("crypto_screening_prefetch cancelled during funding run_id=%s", run_id)
                    return
                flush(units_total, units_total)
            else:
                flush(symbol_count, units_total)

            narrative_result("Подготовка данных завершена — запуск отбора монет (scoring)")
            log_backtest_run_info(
                "PREFETCH | completed — enqueue history_backtest continuation (scoring)",
            )

        from app.core.background_jobs.repository import enqueue_background_job
        from app.core.background_jobs.worker import LANE_HEAVY

        cont_body = dict(body)
        cont_body["skip_crypto_prefetch"] = True
        cont_body["crypto_screening_symbols"] = list(screening_symbols)
        job_id = enqueue_background_job(
            db,
            lane=LANE_HEAVY,
            job_type="history_backtest",
            payload={
                "run_id": run_id,
                "user_id": user_id,
                "body": cont_body,
                "skip_crypto_prefetch": True,
                "crypto_screening_symbols": list(screening_symbols),
            },
            idempotency_key=f"history_backtest:{run_id}:after_prefetch",
        )
        if job_id is None:
            raise RuntimeError(
                f"failed to enqueue history_backtest continuation for run_id={run_id}",
            )
        db.commit()
        logger.info(
            "crypto_screening_prefetch done run_id=%s continuation_job_id=%s",
            run_id,
            job_id,
        )
    except Exception as exc:
        err_msg = f"crypto_screening_prefetch failed: {exc}"[:2000]
        db.rollback()
        try:
            log_backtest_run_exception("PREFETCH | failed run_id=%s", run_id)
            log_backtest_run_error("PREFETCH | %s", err_msg)
            close_backtest_run_log(run_id, status="FAILED", error=err_msg)
        except Exception as log_ex:
            logger.warning("prefetch failure log failed run_id=%s: %s", run_id, log_ex)
        from app.modules.robots.service import _mark_backtest_run_failed

        _mark_backtest_run_failed(db, run_id, err_msg)
        raise
    finally:
        db.close()
