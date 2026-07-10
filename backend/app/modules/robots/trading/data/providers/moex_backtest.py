"""MOEX gap-fill для history-backtest через DmsService (единственная точка httpx/MOEX для свечей)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from app.modules.robots.backtest_progress import touch_backtest_progress_runtime
from app.modules.robots.trading.data.stats import CandlePrefetchStats, GapFillResult
from app.modules.robots.trading.intervals import MOEX_CANDLE_INTERVAL_CODES, ResolvedInterval

logger = logging.getLogger(__name__)

DEFAULT_PREFETCH_BATCH_SIZE = 8


async def ensure_candles_moex_backtest(
    db: Session,
    *,
    board: str,
    tickers: List[str],
    resolved: ResolvedInterval,
    from_date: date,
    till_date: date,
    user_id: Optional[int] = None,
    run_id: Optional[int] = None,
    batch_size: int = DEFAULT_PREFETCH_BATCH_SIZE,
    is_cancelled: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> CandlePrefetchStats:
    from app.modules.dms.service import dms_service

    stats = CandlePrefetchStats(
        total_tickers=len(tickers),
        interval_label=resolved.cache_label,
        moex_interval_code=resolved.moex_interval_code,
    )
    if not tickers:
        return stats

    if resolved.moex_interval_code not in MOEX_CANDLE_INTERVAL_CODES:
        logger.info(
            "candle prefetch skipped: interval=%s moex_code=%s not in MOEX set",
            resolved.cache_label,
            resolved.moex_interval_code,
        )
        stats.skipped_unsupported_interval = True
        return stats

    uniq = sorted({str(t).strip().upper() for t in tickers if t})
    stats.total_tickers = len(uniq)
    bs = max(1, int(batch_size))

    def _touch() -> None:
        if run_id is not None:
            touch_backtest_progress_runtime(run_id)

    def _progress(done: int) -> None:
        stats.processed_tickers = done
        _touch()
        if progress_callback:
            try:
                progress_callback(done, stats.total_tickers)
            except Exception:
                pass

    _progress(0)

    for batch_start in range(0, len(uniq), bs):
        if is_cancelled and is_cancelled():
            stats.cancelled = True
            break
        batch = uniq[batch_start: batch_start + bs]
        batch_done_base = batch_start

        def _on_ticker(local_idx: int, _total: int, _tk: str) -> None:
            _progress(min(stats.total_tickers, batch_done_base + local_idx))

        batch_stats = await dms_service._ensure_candles_cached_for_tickers(
            db,
            board=board,
            tickers=batch,
            interval_code=resolved.moex_interval_code,
            days_back=max(1, (till_date - from_date).days + 1),
            from_date=from_date,
            till_date=till_date,
            refresh_recent_intraday=False,
            min_candles_per_ticker=resolved.min_required_candles,
            user_id=user_id,
            cancel_check=is_cancelled,
            on_ticker_processed=_on_ticker,
        )
        stats.cache_full_hits += int(batch_stats.get("cache_full_hits") or 0)
        stats.fetched_tickers += int(batch_stats.get("fetched_tickers") or 0)
        stats.fetched_ranges += int(batch_stats.get("fetched_ranges") or 0)
        stats.fetched_candles += int(batch_stats.get("fetched_candles") or 0)
        _progress(min(stats.total_tickers, batch_start + len(batch)))

        if is_cancelled and is_cancelled():
            stats.cancelled = True
            break

    if not stats.cancelled:
        stats.processed_tickers = stats.total_tickers

    logger.info("history backtest candle prefetch: %s", stats.summary())
    return stats


async def gap_fill_ticker_moex(
    db: Session,
    *,
    board: str,
    ticker: str,
    interval_code: str,
    interval_code_num: int,
    from_day: date,
    to_day: date,
    user_id: Optional[int] = None,
) -> GapFillResult:
    """Догрузка одного тикера из MOEX в candles_cache при нехватке баров."""
    from app.modules.dms.service import dms_service

    result = GapFillResult(attempted=True)
    try:
        moex_candles = await dms_service._fetch_moex_candles(
            db,
            board=board,
            ticker=ticker,
            interval_code=interval_code_num,
            days_back=max(5, (to_day - from_day).days + 1),
            from_date=from_day.isoformat(),
            till_date=to_day.isoformat(),
            user_id=user_id,
        )
        if moex_candles:
            dms_service._upsert_candles_cache(
                db,
                ticker=ticker,
                interval_label=interval_code,
                candles=moex_candles,
            )
            db.commit()
            result.success = True
            result.row_count = len(moex_candles)
    except Exception:
        result.success = False
    return result


__all__ = [
    "DEFAULT_PREFETCH_BATCH_SIZE",
    "ensure_candles_moex_backtest",
    "gap_fill_ticker_moex",
]
