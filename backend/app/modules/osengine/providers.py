"""Провайдеры за OsEngineFacade: history ingest и lease store."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.osengine.stats import CacheGcStats
from app.modules.osengine.types import CacheLease, InstrumentKey, TimeRange

logger = logging.getLogger(__name__)

DownloadProgressCallback = Callable[[float], None]


@runtime_checkable
class OsEngineHistoryProvider(Protocol):
    """Загрузка недостающих свечей из OsEngine (файлы / bridge) → candles_cache."""

    async def fetch_candle_gaps(
        self,
        db: Session,
        *,
        instrument: InstrumentKey,
        interval: str,
        gaps: List[TimeRange],
        progress_callback: Optional[DownloadProgressCallback] = None,
    ) -> int:
        """Возвращает число upsert-нутых свечей. progress_callback: 0..100 OsData %."""
        ...


@runtime_checkable
class OsEngineLeaseStore(Protocol):
    def create_leases(
        self,
        db: Session,
        *,
        run_id: int,
        market: str,
        instrument_ids: List[str],
        interval: str,
        window: TimeRange,
    ) -> int: ...

    def schedule_expiry(
        self,
        db: Session,
        *,
        run_id: int,
        ttl: timedelta,
    ) -> int: ...

    def list_active_coverage(
        self,
        db: Session,
        *,
        market: str,
        instrument_id: str,
        interval: str,
    ) -> List[TimeRange]: ...

    def gc_unreferenced(self, db: Session, *, market: str, now: Optional[datetime] = None) -> CacheGcStats: ...


class UnconfiguredHistoryProvider:
    """Пока bridge/file importer не подключены — не ходим во внешние API."""

    async def fetch_candle_gaps(
        self,
        db: Session,
        *,
        instrument: InstrumentKey,
        interval: str,
        gaps: List[TimeRange],
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> int:
        if not gaps:
            return 0
        logger.warning(
            "osengine history provider not configured; skip fetch instrument=%s interval=%s gaps=%s data_root=%s",
            instrument.osengine_security_id,
            interval,
            [(g.start.isoformat(), g.end.isoformat()) for g in gaps],
            settings.OSENGINE_DATA_ROOT,
        )
        return 0


class InMemoryLeaseStore:
    """Dev/test lease store. Prod default: PgLeaseStore."""

    def __init__(self) -> None:
        self._leases: List[CacheLease] = []
        self._next_id = 1

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
        n = 0
        for iid in instrument_ids:
            self._leases.append(
                CacheLease(
                    id=self._next_id,
                    run_id=run_id,
                    market=market,
                    instrument_id=iid,
                    interval=interval,
                    from_date=w.start,
                    to_date=w.end,
                    status="active",
                    expires_at=None,
                )
            )
            self._next_id += 1
            n += 1
        return n

    def schedule_expiry(self, db: Session, *, run_id: int, ttl: timedelta) -> int:
        expires = datetime.now(timezone.utc) + ttl
        n = 0
        updated: List[CacheLease] = []
        for lease in self._leases:
            if lease.run_id == run_id and lease.status == "active":
                updated.append(
                    CacheLease(
                        id=lease.id,
                        run_id=lease.run_id,
                        market=lease.market,
                        instrument_id=lease.instrument_id,
                        interval=lease.interval,
                        from_date=lease.from_date,
                        to_date=lease.to_date,
                        status="cooling",
                        expires_at=expires,
                    )
                )
                n += 1
            else:
                updated.append(lease)
        self._leases = updated
        return n

    def list_active_coverage(
        self,
        db: Session,
        *,
        market: str,
        instrument_id: str,
        interval: str,
    ) -> List[TimeRange]:
        now = datetime.now(timezone.utc)
        out: List[TimeRange] = []
        for lease in self._leases:
            if lease.market != market or lease.instrument_id != instrument_id or lease.interval != interval:
                continue
            if lease.status == "expired":
                continue
            if lease.status == "cooling" and lease.expires_at is not None and lease.expires_at <= now:
                continue
            if lease.status == "active" or lease.status == "cooling":
                out.append(TimeRange(start=lease.from_date, end=lease.to_date))
        return out

    def gc_unreferenced(self, db: Session, *, market: str, now: Optional[datetime] = None) -> CacheGcStats:
        ts = now or datetime.now(timezone.utc)
        kept: List[CacheLease] = []
        expired = 0
        for lease in self._leases:
            if lease.market != market:
                kept.append(lease)
                continue
            if lease.status == "cooling" and lease.expires_at is not None and lease.expires_at <= ts:
                expired += 1
                continue
            if lease.status == "expired":
                expired += 1
                continue
            kept.append(lease)
        self._leases = kept
        return CacheGcStats(expired_leases=expired, deleted_candle_rows=0)


def default_history_provider() -> OsEngineHistoryProvider:
    from app.modules.osengine.file_index import resolve_data_root
    from app.modules.osengine.history_files import FileHistoryProvider

    mcp_url = (getattr(settings, "OSENGINE_MCP_URL", None) or "").strip()
    if mcp_url:
        from app.modules.osengine.history_mcp import McpHistoryProvider

        # MCP заказывает дыры; файлы всё равно нужны для upsert в PG.
        return McpHistoryProvider(files=FileHistoryProvider())
    if resolve_data_root() is not None:
        return FileHistoryProvider()
    return UnconfiguredHistoryProvider()


def default_lease_store() -> OsEngineLeaseStore:
    from app.modules.osengine.lease_store import PgLeaseStore

    return PgLeaseStore()


def lease_ttl_for_outcome(*, success: bool) -> timedelta:
    hours = settings.OSENGINE_CACHE_TTL_HOURS if success else settings.OSENGINE_CACHE_TTL_FAIL_HOURS
    return timedelta(hours=float(hours))


__all__ = [
    "InMemoryLeaseStore",
    "OsEngineHistoryProvider",
    "OsEngineLeaseStore",
    "UnconfiguredHistoryProvider",
    "default_history_provider",
    "default_lease_store",
    "lease_ttl_for_outcome",
]
