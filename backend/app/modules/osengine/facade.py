"""
OsEngineFacade — единственная точка взаимодействия GIN ↔ OsEngine market data.

Ответственность:
- ensure свечей под бэктест с lease и gap-only догрузкой;
- release/GC кэша после TTL;
- статус live-ingest (bridge);
- чтение из candles_cache (market=osengine).

MOEX ISS / T-Invest сюда не ходят. History: MCP OsData (gaps) → Data/ → candles_cache.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.osengine.coverage import expand_lookback, merge_ranges, missing_ranges
from app.modules.osengine.lease_store import list_cache_day_coverage
from app.modules.osengine.providers import (
    OsEngineHistoryProvider,
    OsEngineLeaseStore,
    default_history_provider,
    default_lease_store,
    lease_ttl_for_outcome,
)
from app.modules.osengine.stats import (
    CacheGcStats,
    EnsureCandlesStats,
    LeaseReleaseStats,
    LiveIngestStatus,
)
from app.modules.osengine.types import CandleEnsureRequest, InstrumentKey, TimeRange
from app.modules.robots.trading.data.providers.db_cache import (
    query_candles_cache_rows,
    query_candles_cache_rows_bulk,
)

logger = logging.getLogger(__name__)

_default_facade: Optional["DefaultOsEngineFacade"] = None


@runtime_checkable
class OsEngineFacade(Protocol):
    async def ensure_candles_for_backtest(
        self,
        db: Session,
        request: CandleEnsureRequest,
        *,
        is_cancelled: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> EnsureCandlesStats: ...

    def release_backtest_leases(
        self,
        db: Session,
        *,
        run_id: int,
        success: bool = True,
    ) -> LeaseReleaseStats: ...

    def gc_cache(self, db: Session) -> CacheGcStats: ...

    def live_status(self, db: Optional[Session] = None) -> LiveIngestStatus: ...

    def read_candles_cache_rows(
        self,
        db: Session,
        *,
        instrument_id: str | None = None,
        ticker: str,
        interval_code: str,
        interval_code_num: int,
        from_dt: datetime,
        to_dt_exclusive: datetime,
    ) -> List[Any]: ...

    def read_candles_cache_rows_bulk(
        self,
        db: Session,
        *,
        instrument_ids: List[str],
        interval_code: str,
        interval_code_num: int,
        from_dt: datetime,
        to_dt_exclusive: datetime,
        batch_size: int = 200,
    ) -> Dict[str, List[Any]]: ...


CoverageLookup = Callable[
    [Session, str, str, str, TimeRange],
    List[TimeRange],
]


def _default_coverage_lookup(
    db: Session,
    market: str,
    instrument_id: str,
    interval: str,
    window: TimeRange,
) -> List[TimeRange]:
    return list_cache_day_coverage(
        db,
        market=market,
        instrument_id=instrument_id,
        interval=interval,
        window=window,
        candle_tz=str(getattr(settings, "OSENGINE_CANDLE_TZ", None) or "Europe/Moscow"),
    )


class DefaultOsEngineFacade:
    """Оркестрация: cache coverage → history gaps → leases. Без MOEX/T-Invest."""

    def __init__(
        self,
        *,
        history: Optional[OsEngineHistoryProvider] = None,
        leases: Optional[OsEngineLeaseStore] = None,
        market: Optional[str] = None,
        coverage_lookup: Optional[CoverageLookup] = None,
    ) -> None:
        self._history = history or default_history_provider()
        self._leases = leases or default_lease_store()
        self._market = (market or settings.OSENGINE_MARKET_KEY).strip() or "osengine"
        self._coverage_lookup = coverage_lookup or _default_coverage_lookup

    @property
    def market(self) -> str:
        return self._market

    @property
    def enabled(self) -> bool:
        return bool(settings.OSENGINE_ENABLED)

    async def ensure_candles_for_backtest(
        self,
        db: Session,
        request: CandleEnsureRequest,
        *,
        is_cancelled: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> EnsureCandlesStats:
        # GC по триггеру старта бэктеста: чистим просроченные lease/кэш до нового ensure.
        if settings.OSENGINE_CACHE_GC_ON_BACKTEST_START:
            try:
                gc_stats = self.gc_cache(db)
                if gc_stats.expired_leases or gc_stats.deleted_candle_rows:
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                        logger.warning(
                            "osengine gc commit failed before ensure run_id=%s",
                            request.run_id,
                            exc_info=True,
                        )
            except Exception:
                logger.warning(
                    "osengine gc on backtest start failed run_id=%s — continue ensure",
                    request.run_id,
                    exc_info=True,
                )

        window = expand_lookback(request.window, request.lookback_days)
        instruments = [k.normalized() for k in request.instruments if (k.ticker or "").strip()]
        stats = EnsureCandlesStats(
            run_id=request.run_id,
            interval=request.interval,
            total_instruments=len(instruments),
        )
        if not instruments:
            return stats

        instrument_ids: List[str] = []
        for idx, instrument in enumerate(instruments):
            if is_cancelled and is_cancelled():
                stats.cancelled = True
                break
            iid = instrument.cache_id
            instrument_ids.append(iid)

            # Покрытие = фактические дни в candles_cache (пересечение бэктестов = общий кэш).
            # Lease только удерживает данные от GC, на fetch не влияет.
            try:
                covered = self._coverage_lookup(
                    db, self._market, iid, request.interval, window
                )
            except Exception as exc:
                logger.warning(
                    "osengine cache coverage failed instrument=%s: %s — treat as empty",
                    iid,
                    exc,
                )
                covered = []
            gaps = missing_ranges(window, merge_ranges(covered))
            if not gaps:
                stats.cache_full_hits += 1
            else:
                stats.instruments_with_gaps += 1
                stats.fetched_ranges += len(gaps)
                if len(stats.gap_samples) < 8:
                    stats.gap_samples.extend(gaps[: max(0, 8 - len(stats.gap_samples))])

                def _on_download_pct(pct: float, *, _idx: int = idx, _n: int = len(instruments)) -> None:
                    if not progress_callback:
                        return
                    # Scale: each ticker = 100 units; OsData percent moves within the current ticker.
                    try:
                        progress_callback(
                            _idx * 100 + min(99, max(0, int(pct))),
                            _n * 100,
                        )
                    except Exception:
                        pass

                try:
                    n = await self._history.fetch_candle_gaps(
                        db,
                        instrument=instrument,
                        interval=request.interval,
                        gaps=gaps,
                        progress_callback=_on_download_pct,
                    )
                    stats.fetched_candles += int(n or 0)
                    if n == 0 and gaps:
                        stats.skipped_provider_unavailable = True
                except Exception as exc:
                    stats.errors += 1
                    stats.last_error = str(exc)
                    logger.exception(
                        "osengine ensure fetch failed instrument=%s interval=%s",
                        iid,
                        request.interval,
                    )

            if progress_callback:
                try:
                    # Prefer 0..N*100 scale when OsEngine path (download pct uses same scale).
                    progress_callback((idx + 1) * 100, len(instruments) * 100)
                except Exception:
                    pass

        if instrument_ids and not stats.cancelled:
            stats.leases_created = self._leases.create_leases(
                db,
                run_id=request.run_id,
                market=self._market,
                instrument_ids=instrument_ids,
                interval=request.interval,
                window=window,
            )
        logger.info("%s", stats.summary())
        return stats

    def release_backtest_leases(
        self,
        db: Session,
        *,
        run_id: int,
        success: bool = True,
    ) -> LeaseReleaseStats:
        ttl = lease_ttl_for_outcome(success=success)
        n = self._leases.schedule_expiry(db, run_id=run_id, ttl=ttl)
        expires = datetime.now(timezone.utc) + ttl
        stats = LeaseReleaseStats(
            run_id=run_id,
            leases_touched=n,
            expires_at_iso=expires.isoformat(),
        )
        logger.info(
            "osengine leases cooling run_id=%s touched=%s ttl_h=%.2f success=%s",
            run_id,
            n,
            ttl.total_seconds() / 3600.0,
            success,
        )
        return stats

    def gc_cache(self, db: Session) -> CacheGcStats:
        stats = self._leases.gc_unreferenced(db, market=self._market)
        logger.info(
            "osengine cache gc market=%s expired_leases=%s deleted_candles=%s",
            self._market,
            stats.expired_leases,
            stats.deleted_candle_rows,
        )
        return stats

    def live_status(self, db: Optional[Session] = None) -> LiveIngestStatus:
        if db is None:
            return LiveIngestStatus(
                enabled=self.enabled,
                bridge_connected=False,
                detail="pass db session for heartbeat status",
            )
        from app.modules.osengine.ingest import read_live_status

        return read_live_status(db)

    def read_candles_cache_rows(
        self,
        db: Session,
        *,
        instrument_id: str | None = None,
        ticker: str,
        interval_code: str,
        interval_code_num: int,
        from_dt: datetime,
        to_dt_exclusive: datetime,
    ) -> List[Any]:
        return query_candles_cache_rows(
            db,
            market=self._market,
            instrument_id=instrument_id,
            ticker=ticker,
            interval_code=interval_code,
            interval_code_num=interval_code_num,
            from_dt=from_dt,
            to_dt_exclusive=to_dt_exclusive,
        )

    def read_candles_cache_rows_bulk(
        self,
        db: Session,
        *,
        instrument_ids: List[str],
        interval_code: str,
        interval_code_num: int,
        from_dt: datetime,
        to_dt_exclusive: datetime,
        batch_size: int = 200,
    ) -> Dict[str, List[Any]]:
        return query_candles_cache_rows_bulk(
            db,
            market=self._market,
            instrument_ids=instrument_ids,
            interval_code=interval_code,
            interval_code_num=interval_code_num,
            from_dt=from_dt,
            to_dt_exclusive=to_dt_exclusive,
            batch_size=batch_size,
        )


def build_candle_ensure_request(
    *,
    run_id: int,
    tickers: Sequence[str],
    interval: str,
    from_date: date,
    till_date: date,
    board: str = "TQBR",
    lookback_days: int = 0,
) -> CandleEnsureRequest:
    keys = tuple(
        InstrumentKey(ticker=t, board=board).normalized()
        for t in tickers
        if (t or "").strip()
    )
    return CandleEnsureRequest(
        run_id=run_id,
        instruments=keys,
        interval=interval,
        window=TimeRange(start=from_date, end=till_date),
        lookback_days=lookback_days,
    )


def get_osengine_facade() -> DefaultOsEngineFacade:
    global _default_facade
    if _default_facade is None:
        _default_facade = DefaultOsEngineFacade()
    return _default_facade


def reset_osengine_facade_for_tests() -> None:
    """Сброс singleton (unit-tests)."""
    global _default_facade
    _default_facade = None


__all__ = [
    "DefaultOsEngineFacade",
    "OsEngineFacade",
    "build_candle_ensure_request",
    "get_osengine_facade",
    "reset_osengine_facade_for_tests",
]
