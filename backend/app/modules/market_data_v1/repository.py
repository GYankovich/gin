"""Репозиторий shared_market_candles и candle_load_jobs [ref: ARCH-01]."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import Text, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from app.core.config import settings


def _schema() -> str:
    return settings.DB_SCHEMA


def coverage_bounds(
        db: Session,
        ticker: str,
        board: str,
        interval: str,
        from_ts: datetime,
        to_ts: datetime,
) -> Optional[Tuple[datetime, datetime]]:
    row = db.execute(
        text(f"""
            SELECT MIN(bucket_start), MAX(bucket_start)
            FROM {_schema()}.shared_market_candles
            WHERE ticker = :ticker
              AND board = :board
              AND interval = :interval
              AND bucket_start >= :from_ts
              AND bucket_start <= :to_ts
        """),
        {
            "ticker": ticker.upper(),
            "board": board.upper(),
            "interval": interval,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    ).first()
    if not row or row[0] is None:
        return None
    return row[0], row[1]


def count_buckets_in_window(
        db: Session,
        ticker: str,
        board: str,
        interval: str,
        from_ts: datetime,
        to_ts: datetime,
) -> int:
    row = db.execute(
        text(f"""
            SELECT COUNT(*)::bigint
            FROM {_schema()}.shared_market_candles
            WHERE ticker = :ticker
              AND board = :board
              AND interval = :interval
              AND bucket_start >= :from_ts
              AND bucket_start <= :to_ts
        """),
        {
            "ticker": ticker.upper(),
            "board": board.upper(),
            "interval": interval,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    ).scalar()
    return int(row or 0)


def list_bucket_starts_in_window(
        db: Session,
        ticker: str,
        board: str,
        interval: str,
        from_ts: datetime,
        to_ts: datetime,
) -> List[datetime]:
    rows = db.execute(
        text(f"""
            SELECT bucket_start
            FROM {_schema()}.shared_market_candles
            WHERE ticker = :ticker
              AND board = :board
              AND interval = :interval
              AND bucket_start >= :from_ts
              AND bucket_start <= :to_ts
            ORDER BY bucket_start ASC
        """),
        {
            "ticker": ticker.upper(),
            "board": board.upper(),
            "interval": interval,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    ).fetchall()
    return [r[0] for r in rows]


def upsert_shared_candles(
        db: Session,
        *,
        ticker: str,
        board: str,
        interval: str,
        rows: List[Tuple[datetime, Decimal, Decimal, Decimal, Decimal, Optional[int]]],
) -> int:
    if not rows:
        return 0
    q = text(f"""
        INSERT INTO {_schema()}.shared_market_candles
            (ticker, board, interval, bucket_start, open, high, low, close, volume, source, updated_at)
        VALUES
            (:ticker, :board, :interval, :bucket_start, :open, :high, :low, :close, :volume, 'MOEX_ISS', CURRENT_TIMESTAMP)
        ON CONFLICT (ticker, board, interval, bucket_start) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            updated_at = CURRENT_TIMESTAMP
    """)
    n = 0
    tku = ticker.upper()
    bu = board.upper()
    for ts, o, h, l, c, vol in rows:
        db.execute(
            q,
            {
                "ticker": tku,
                "board": bu,
                "interval": interval,
                "bucket_start": ts,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": vol,
            },
        )
        n += 1
    return n


def insert_job(
        db: Session,
        *,
        user_id: int,
        board: str,
        interval: str,
        from_ts: datetime,
        to_ts: datetime,
        tickers: List[str],
        idempotency_key: Optional[str],
) -> UUID:
    tickers_u = [t.strip().upper() for t in tickers if t and str(t).strip()]
    if idempotency_key:
        row = db.execute(
            text(f"""
                SELECT id FROM {_schema()}.candle_load_jobs
                WHERE idempotency_key = :ik
                LIMIT 1
            """),
            {"ik": idempotency_key[:128]},
        ).first()
        if row:
            return row[0]

    ins = text(
        f"""
            INSERT INTO {_schema()}.candle_load_jobs
                (user_id, status, board, interval, from_ts, to_ts, tickers, tickers_total, idempotency_key)
            VALUES
                (:user_id, 'queued', :board, :interval, :from_ts, :to_ts, :tickers, :tickers_total, :idempotency_key)
            RETURNING id
        """
    ).bindparams(bindparam("tickers", type_=ARRAY(Text())))
    row = db.execute(
        ins,
        {
            "user_id": user_id,
            "board": board.upper(),
            "interval": interval,
            "from_ts": from_ts,
            "to_ts": to_ts,
            "tickers": tickers_u,
            "tickers_total": len(tickers_u),
            "idempotency_key": idempotency_key[:128] if idempotency_key else None,
        },
    ).scalar()
    return row


def get_job(db: Session, job_id: UUID, user_id: int) -> Optional[Dict[str, Any]]:
    row = db.execute(
        text(f"""
            SELECT id, user_id, status, board, interval, from_ts, to_ts, tickers,
                   tickers_total, tickers_done, bars_written, progress_percent,
                   message, eta_seconds, error, created_at, updated_at, started_at, finished_at
            FROM {_schema()}.candle_load_jobs
            WHERE id = :id AND user_id = :user_id
        """),
        {"id": job_id, "user_id": user_id},
    ).mappings().first()
    if not row:
        return None
    return dict(row)


def claim_next_queued_job(db: Session) -> Optional[Dict[str, Any]]:
    row = db.execute(
        text(f"""
            WITH c AS (
                SELECT id
                FROM {_schema()}.candle_load_jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE {_schema()}.candle_load_jobs j
            SET status = 'running',
                started_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                message = 'MOEX: starting'
            FROM c
            WHERE j.id = c.id
            RETURNING j.id, j.user_id, j.board, j.interval, j.from_ts, j.to_ts, j.tickers,
                      j.tickers_total, j.tickers_done, j.bars_written
        """),
    ).mappings().first()
    if not row:
        return None
    return dict(row)


def update_job_progress(
        db: Session,
        job_id: UUID,
        *,
        tickers_done: int,
        bars_written: int,
        progress_percent: float,
        message: Optional[str],
        eta_seconds: Optional[int],
) -> None:
    db.execute(
        text(f"""
            UPDATE {_schema()}.candle_load_jobs
            SET tickers_done = :tickers_done,
                bars_written = :bars_written,
                progress_percent = :progress_percent,
                message = :message,
                eta_seconds = :eta_seconds,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """),
        {
            "id": job_id,
            "tickers_done": tickers_done,
            "bars_written": bars_written,
            "progress_percent": progress_percent,
            "message": message,
            "eta_seconds": eta_seconds,
        },
    )


def complete_job(db: Session, job_id: UUID) -> None:
    db.execute(
        text(f"""
            UPDATE {_schema()}.candle_load_jobs
            SET status = 'completed',
                progress_percent = 100,
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                message = 'completed',
                eta_seconds = 0
            WHERE id = :id
        """),
        {"id": job_id},
    )


def fail_job(db: Session, job_id: UUID, error: str) -> None:
    db.execute(
        text(f"""
            UPDATE {_schema()}.candle_load_jobs
            SET status = 'failed',
                error = :err,
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                message = 'failed'
            WHERE id = :id
        """),
        {"id": job_id, "err": error[:8000]},
    )


def list_candles(
        db: Session,
        *,
        tickers: List[str],
        board: str,
        interval: str,
        from_ts: datetime,
        to_ts: datetime,
) -> List[Dict[str, Any]]:
    """Одна выборка по нескольким тикерам (OR)."""
    if not tickers:
        return []
    tickers_u = [t.strip().upper() for t in tickers]
    q = text(
        f"""
        SELECT ticker, board, interval, bucket_start, open, high, low, close, volume, source
        FROM {_schema()}.shared_market_candles
        WHERE board = :board
          AND interval = :interval
          AND ticker = ANY(:tickers)
          AND bucket_start >= :from_ts
          AND bucket_start <= :to_ts
        ORDER BY ticker ASC, bucket_start ASC
    """
    ).bindparams(bindparam("tickers", type_=ARRAY(Text())))
    rows = db.execute(
        q,
        {
            "board": board.upper(),
            "interval": interval,
            "tickers": tickers_u,
            "from_ts": from_ts,
            "to_ts": to_ts,
        },
    ).mappings().all()
    return [dict(r) for r in rows]
