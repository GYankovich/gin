"""PostgreSQL lease store + GC для candles_cache (market-scoped)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.osengine.coverage import merge_ranges
from app.modules.osengine.stats import CacheGcStats
from app.modules.osengine.types import TimeRange

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PgLeaseStore:
    """Persist leases in market_cache_leases; GC deletes unreferenced candles_cache rows."""

    def create_leases(
        self,
        db: Session,
        *,
        run_id: int,
        market: str,
        instrument_ids: List[str],
        interval: str,
        window: TimeRange,
    ) -> int:
        w = window.normalized()
        if not instrument_ids or w.start == w.end:
            return 0
        n = 0
        for iid in instrument_ids:
            db.execute(
                text(
                    """
                    INSERT INTO market_cache_leases
                        (run_id, market, instrument_id, interval, from_date, to_date, status, expires_at)
                    VALUES
                        (:run_id, :market, :instrument_id, :interval, :from_date, :to_date, 'active', NULL)
                    """
                ),
                {
                    "run_id": int(run_id),
                    "market": market,
                    "instrument_id": iid,
                    "interval": interval,
                    "from_date": w.start,
                    "to_date": w.end,
                },
            )
            n += 1
        db.flush()
        return n

    def schedule_expiry(self, db: Session, *, run_id: int, ttl: timedelta) -> int:
        expires = _now() + ttl
        result = db.execute(
            text(
                """
                UPDATE market_cache_leases
                   SET status = 'cooling',
                       expires_at = :expires_at,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE run_id = :run_id
                   AND status = 'active'
                """
            ),
            {"run_id": int(run_id), "expires_at": expires},
        )
        db.flush()
        return int(result.rowcount or 0)

    def list_active_coverage(
        self,
        db: Session,
        *,
        market: str,
        instrument_id: str,
        interval: str,
    ) -> List[TimeRange]:
        """Lease windows still protecting data (active or not-yet-expired cooling)."""
        rows = db.execute(
            text(
                """
                SELECT from_date, to_date
                  FROM market_cache_leases
                 WHERE market = :market
                   AND instrument_id = :instrument_id
                   AND interval = :interval
                   AND (
                        status = 'active'
                        OR (status = 'cooling' AND expires_at IS NOT NULL AND expires_at > :now)
                   )
                """
            ),
            {
                "market": market,
                "instrument_id": instrument_id,
                "interval": interval,
                "now": _now(),
            },
        ).fetchall()
        ranges = [
            TimeRange(start=r[0], end=r[1])
            for r in rows
            if r[0] is not None and r[1] is not None
        ]
        return merge_ranges(ranges)

    def gc_unreferenced(self, db: Session, *, market: str, now: Optional[datetime] = None) -> CacheGcStats:
        ts = now or _now()
        expired = db.execute(
            text(
                """
                UPDATE market_cache_leases
                   SET status = 'expired',
                       updated_at = CURRENT_TIMESTAMP
                 WHERE market = :market
                   AND status = 'cooling'
                   AND expires_at IS NOT NULL
                   AND expires_at <= :now
                """
            ),
            {"market": market, "now": ts},
        )
        expired_n = int(expired.rowcount or 0)

        # Удаляем свечи market, не попадающие ни в одно живое lease-окно (даты — календарь MSK).
        tz = str(getattr(settings, "OSENGINE_CANDLE_TZ", None) or "Europe/Moscow").strip()
        if tz not in ("Europe/Moscow", "UTC", "Europe/Samara"):
            tz = "Europe/Moscow"
        deleted = db.execute(
            text(
                f"""
                DELETE FROM candles_cache c
                 WHERE c.market = :market
                   AND NOT EXISTS (
                        SELECT 1
                          FROM market_cache_leases l
                         WHERE l.market = c.market
                           AND l.instrument_id = c.instrument_id
                           AND l.interval = c.interval
                           AND (
                                l.status = 'active'
                                OR (l.status = 'cooling' AND l.expires_at IS NOT NULL AND l.expires_at > :now)
                           )
                           AND (c.candle_time AT TIME ZONE '{tz}')::date >= l.from_date
                           AND (c.candle_time AT TIME ZONE '{tz}')::date < l.to_date
                   )
                """
            ),
            {"market": market, "now": ts},
        )
        deleted_n = int(deleted.rowcount or 0)
        db.flush()
        if expired_n or deleted_n:
            logger.info(
                "market_cache_leases gc market=%s expired_leases=%s deleted_candles=%s",
                market,
                expired_n,
                deleted_n,
            )
        return CacheGcStats(
            expired_leases=expired_n,
            deleted_candle_rows=deleted_n,
        )


def list_cache_day_coverage(
    db: Session,
    *,
    market: str,
    instrument_id: str,
    interval: str,
    window: TimeRange,
    candle_tz: str = "Europe/Moscow",
) -> List[TimeRange]:
    """Покрытие по календарным дням в candle_tz (обычно MSK для OsEngine/MOEX)."""
    w = window.normalized()
    if w.start == w.end:
        return []
    # AT TIME ZONE с параметром нельзя надёжно биндить во всех драйверах —
    # whitelist известных TZ.
    tz = (candle_tz or "Europe/Moscow").strip()
    if tz not in ("Europe/Moscow", "UTC", "Europe/Samara"):
        tz = "Europe/Moscow"
    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT ((candle_time AT TIME ZONE '{tz}')::date) AS d
              FROM candles_cache
             WHERE market = :market
               AND instrument_id = :instrument_id
               AND interval = :interval
               AND (candle_time AT TIME ZONE '{tz}')::date >= :from_d
               AND (candle_time AT TIME ZONE '{tz}')::date < :to_d
             ORDER BY 1
            """
        ),
        {
            "market": market,
            "instrument_id": instrument_id,
            "interval": interval,
            "from_d": w.start,
            "to_d": w.end,
        },
    ).fetchall()
    days = [r[0] for r in rows if isinstance(r[0], date)]
    if not days:
        return []
    from datetime import timedelta

    ranges: List[TimeRange] = []
    block_start = days[0]
    prev = days[0]
    for d in days[1:]:
        if d == prev + timedelta(days=1):
            prev = d
            continue
        ranges.append(TimeRange(start=block_start, end=prev + timedelta(days=1)))
        block_start = d
        prev = d
    ranges.append(TimeRange(start=block_start, end=prev + timedelta(days=1)))
    return merge_ranges(ranges)


__all__ = ["PgLeaseStore", "list_cache_day_coverage"]
