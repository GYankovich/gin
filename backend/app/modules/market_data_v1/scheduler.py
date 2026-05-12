"""Фоновый воркер очереди candle_load_jobs: MOEX → shared_market_candles [ref: ARCH-01]."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging_config import get_logger
from app.modules.market_data_v1 import repository
from app.modules.market_data_v1 import gaps as gap_util
from app.modules.market_data_v1.intervals import moex_interval_code
from app.modules.market_data_v1.moex_fetch import fetch_moex_candles_range

system_log = get_logger("market_data_v1.scheduler")


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def process_claimed_job(db: Session, job: Dict[str, Any]) -> None:
    job_id: UUID = job["id"]
    board = str(job["board"])
    interval = str(job["interval"])
    from_ts: datetime = _utc(job["from_ts"])
    to_ts: datetime = _utc(job["to_ts"])
    tickers_raw = job["tickers"]
    tickers = [str(t).strip().upper() for t in (tickers_raw or []) if str(t).strip()]
    tickers_total = int(job["tickers_total"]) or len(tickers)
    moex_code = moex_interval_code(interval)

    bars_written = int(job.get("bars_written") or 0)
    avg_sec_per_ticker = 8.0
    alpha = 0.35
    max_bucket_rows = 1_200_000

    for idx, ticker in enumerate(tickers):
        ticker_t0 = time.monotonic()
        try:
            cnt = repository.count_buckets_in_window(
                db, ticker, board, interval, from_ts, to_ts,
            )
            if cnt > max_bucket_rows:
                system_log.warning(
                    "candle job %s ticker %s: bucket rows=%s > %s, full MOEX range fallback",
                    job_id,
                    ticker,
                    cnt,
                    max_bucket_rows,
                )
                fetch_ranges = [(from_ts, to_ts)]
            else:
                existing = repository.list_bucket_starts_in_window(
                    db, ticker, board, interval, from_ts, to_ts,
                )
                fetch_ranges = gap_util.compute_moex_fetch_ranges(
                    existing, from_ts, to_ts, interval,
                )

            if not fetch_ranges:
                system_log.info(
                    "candle job %s ticker %s: cache covers window, MOEX skipped",
                    job_id,
                    ticker,
                )
                msg = f"MOEX: {ticker} cached {_short_range(from_ts, to_ts)}"
            else:
                total_gaps = len(fetch_ranges)
                rough_eta = int(max(0.0, (tickers_total - idx) * avg_sec_per_ticker))
                for gi, (g_from, g_to) in enumerate(fetch_ranges):
                    msg = (
                        f"MOEX: {ticker} gap {gi + 1}/{total_gaps} "
                        f"{_short_range(g_from, g_to)}"
                    )
                    repository.update_job_progress(
                        db,
                        job_id,
                        tickers_done=idx,
                        bars_written=bars_written,
                        progress_percent=min(
                            ((idx + (gi + 1) / max(total_gaps, 1)) / max(tickers_total, 1)) * 100.0,
                            99.9,
                        ),
                        message=msg,
                        eta_seconds=rough_eta,
                    )
                    db.commit()

                    rows = await fetch_moex_candles_range(
                        ticker,
                        moex_code,
                        g_from,
                        g_to,
                        board_override=board,
                    )
                    n = repository.upsert_shared_candles(
                        db,
                        ticker=ticker,
                        board=board,
                        interval=interval,
                        rows=rows,
                    )
                    bars_written += n
                    await asyncio.sleep(0.15)

                msg = f"MOEX: {ticker} done {_short_range(from_ts, to_ts)} ({total_gaps} gaps)"
        except Exception as e:
            system_log.exception("candle job %s failed on ticker %s: %s", job_id, ticker, e)
            repository.fail_job(db, job_id, f"{ticker}: {e}")
            db.commit()
            return

        elapsed = time.monotonic() - ticker_t0
        avg_sec_per_ticker = alpha * elapsed + (1.0 - alpha) * avg_sec_per_ticker
        tickers_done = idx + 1
        remaining = tickers_total - tickers_done
        eta = int(max(0.0, remaining * avg_sec_per_ticker))
        progress = (tickers_done / max(tickers_total, 1)) * 100.0

        repository.update_job_progress(
            db,
            job_id,
            tickers_done=tickers_done,
            bars_written=bars_written,
            progress_percent=min(progress, 99.9) if tickers_done < tickers_total else 100.0,
            message=msg,
            eta_seconds=eta,
        )
        db.commit()
        await asyncio.sleep(0.2)

    repository.complete_job(db, job_id)
    db.commit()
    system_log.info(
        "candle job %s completed tickers=%s bars=%s",
        job_id,
        tickers_total,
        bars_written,
    )


def _short_range(a: datetime, b: datetime) -> str:
    return f"{a.date().isoformat()}..{b.date().isoformat()}"


async def run_one_queued_job() -> bool:
    """
    Забирает один `queued` job, исполняет до конца или `failed`.
    Возвращает True, если job был взят в работу (включая завершение с ошибкой по тикеру).
    """
    db = SessionLocal()
    job: Optional[Dict[str, Any]] = None
    try:
        job = repository.claim_next_queued_job(db)
        if not job:
            db.rollback()
            return False
        db.commit()
    except Exception as e:
        system_log.error("claim candle job failed: %s", e)
        db.rollback()
        return False
    finally:
        db.close()

    if not job:
        return False

    db2 = SessionLocal()
    try:
        await process_claimed_job(db2, job)
    except Exception as e:
        system_log.exception("process candle job %s: %s", job.get("id"), e)
        try:
            repository.fail_job(db2, job["id"], str(e))
            db2.commit()
        except Exception:
            db2.rollback()
    finally:
        db2.close()

    return True


class CandleLoadScheduler:
    def __init__(self) -> None:
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.poll_seconds = 2.0

    async def _loop(self) -> None:
        system_log.info("candle_load scheduler started, poll=%ss", self.poll_seconds)
        while self.running:
            try:
                worked = await run_one_queued_job()
                if not worked:
                    await asyncio.sleep(self.poll_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_log.error("candle_load scheduler cycle: %s", e)
                await asyncio.sleep(self.poll_seconds)
        system_log.info("candle_load scheduler stopped")

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


candle_load_scheduler = CandleLoadScheduler()


async def start_candle_load_scheduler() -> None:
    await candle_load_scheduler.start()


async def stop_candle_load_scheduler() -> None:
    await candle_load_scheduler.stop()
