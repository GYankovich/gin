"""File-based OsEngine history → candles_cache."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.osengine.candle_parser import ParsedCandle, iter_candles_from_file
from app.modules.osengine.file_index import find_candle_files, resolve_data_root
from app.modules.osengine.intervals_map import normalize_cache_interval
from app.modules.osengine.types import InstrumentKey, TimeRange

logger = logging.getLogger(__name__)


def _gap_bounds_utc(gap: TimeRange, source_tz: str) -> tuple[datetime, datetime]:
    """Полуинтервал gap [start, end) как календарные дни в source_tz → UTC."""
    g = gap.normalized()
    tz = ZoneInfo(source_tz)
    start_local = datetime.combine(g.start, time.min, tzinfo=tz)
    end_local = datetime.combine(g.end, time.min, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def upsert_osengine_candles(
    db: Session,
    *,
    market: str,
    instrument_id: str,
    ticker: str,
    interval: str,
    candles: List[ParsedCandle],
    source: str = "osengine_file",
) -> int:
    if not candles:
        return 0
    wrote = 0
    # дедуп по времени внутри батча (последний выигрывает)
    by_ts: Dict[datetime, ParsedCandle] = {c.time_start: c for c in candles}
    rows = list(by_ts.values())
    chunk = 500
    for off in range(0, len(rows), chunk):
        batch = rows[off : off + chunk]
        for c in batch:
            db.execute(
                text(
                    """
                    INSERT INTO candles_cache
                    (market, instrument_id, ticker, interval, candle_time, open, high, low, close, volume, source, updated_at)
                    VALUES
                    (:market, :instrument_id, :ticker, :interval, :candle_time, :open, :high, :low, :close, :volume, :source, NOW())
                    ON CONFLICT (market, instrument_id, interval, candle_time)
                    DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        source = EXCLUDED.source,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "market": market,
                    "instrument_id": instrument_id,
                    "ticker": ticker,
                    "interval": interval,
                    "candle_time": c.time_start,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": int(c.volume) if c.volume == c.volume.to_integral_value() else float(c.volume),
                    "source": source,
                },
            )
            wrote += 1
    return wrote


class FileHistoryProvider:
    """Читает OsData-сеты с диска и пишет в candles_cache (market=osengine)."""

    def __init__(
        self,
        *,
        data_root: Optional[str] = None,
        market: Optional[str] = None,
        source_tz: Optional[str] = None,
    ) -> None:
        self._data_root = data_root
        self._market = (market or settings.OSENGINE_MARKET_KEY).strip() or "osengine"
        self._source_tz = (source_tz or getattr(settings, "OSENGINE_CANDLE_TZ", None) or "Europe/Moscow").strip()

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
        root = resolve_data_root(self._data_root)
        if root is None:
            logger.warning(
                "osengine file history: OSENGINE_DATA_ROOT not set; skip %s",
                instrument.osengine_security_id,
            )
            return 0

        cache_iv = normalize_cache_interval(interval)
        hits = find_candle_files(root, instrument=instrument, interval=cache_iv)
        if not hits:
            logger.warning(
                "osengine file history: no files for ticker=%s interval=%s root=%s",
                instrument.cache_id,
                cache_iv,
                root,
            )
            return 0

        total = 0
        for gap in gaps:
            g = gap.normalized()
            from_utc, to_utc = _gap_bounds_utc(g, self._source_tz)
            collected: List[ParsedCandle] = []
            for hit in hits:
                try:
                    for candle in iter_candles_from_file(
                        str(hit.path),
                        source_tz=self._source_tz,
                        from_utc=from_utc,
                        to_utc_exclusive=to_utc,
                    ):
                        collected.append(candle)
                except OSError as exc:
                    logger.warning("osengine read failed path=%s: %s", hit.path, exc)
            n = upsert_osengine_candles(
                db,
                market=self._market,
                instrument_id=instrument.cache_id,
                ticker=instrument.normalized().ticker,
                interval=cache_iv,
                candles=collected,
            )
            total += n
            logger.info(
                "osengine file import ticker=%s interval=%s gap=%s..%s files=%s candles=%s",
                instrument.cache_id,
                cache_iv,
                g.start.isoformat(),
                g.end.isoformat(),
                len(hits),
                n,
            )
        if total:
            try:
                db.flush()
            except Exception:
                logger.exception("osengine file history flush failed")
        return total


__all__ = ["FileHistoryProvider", "upsert_osengine_candles"]
