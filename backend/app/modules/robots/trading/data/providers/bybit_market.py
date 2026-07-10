"""ByBit market-data provider: fetch kline/funding and upsert into cache tables."""

from __future__ import annotations

import asyncio
import logging
import time as time_mod
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.bybit.http_client import BybitHttpClient
from app.modules.robots.backtest_progress import touch_backtest_progress_runtime
from app.modules.robots.trading.data.stats import CandlePrefetchStats, FundingPrefetchStats
from app.modules.robots.trading.intervals import ResolvedInterval, strategy_interval_to_bybit_kline

logger = logging.getLogger(__name__)

FUNDING_INTERVAL_SECONDS = 8 * 3600
BYBIT_PUBLIC_API_MIN_INTERVAL_SEC = 0.12
_BYBIT_RATE_LOCK = asyncio.Lock()
_BYBIT_LAST_REQUEST_AT = 0.0

_CANDLES_DAYS_SQL = (
    "SELECT DISTINCT DATE(candle_time AT TIME ZONE 'UTC') AS d "
    f"FROM {settings.DB_SCHEMA}.candles_cache "
    "WHERE market='bybit' AND instrument_id=:symbol AND interval=:interval "
    "AND candle_time>=:from_dt AND candle_time<:to_dt_exclusive"
)
_FUNDING_COVERAGE_SQL = (
    "SELECT COUNT(*) AS cnt, MIN(funding_time) AS min_ft "
    f"FROM {settings.DB_SCHEMA}.bybit_funding_history "
    "WHERE symbol=:symbol AND instrument_category=:instrument_category "
    "AND funding_time>=:from_dt AND funding_time<:to_dt_exclusive"
)


def _log_prefetch_cache(msg: str, *args: Any) -> None:
    try:
        from app.modules.robots.trading.backtest.run_file_logger import log_backtest_run_info

        log_backtest_run_info(msg, *args)
    except Exception:
        pass


@dataclass
class CandlesCacheAudit:
    symbol: str
    interval_label: str
    interval_code: int
    from_date: date
    till_date: date
    expected_days: int
    cached_days_count: int
    cached_min: Optional[date]
    cached_max: Optional[date]
    missing_raw_count: int
    pre_listing_skipped_count: int
    missing_final_count: int
    min_bars_per_day: int = 1
    fetch_ranges: List[Tuple[date, date]] = field(default_factory=list)

    @property
    def action(self) -> str:
        return "HIT" if not self.fetch_ranges else "FETCH"

    def reason(self) -> str:
        if not self.fetch_ranges:
            if self.missing_raw_count > 0 and self.pre_listing_skipped_count > 0:
                return "pre_listing_gap_ignored"
            return "cache_full"
        if self.cached_days_count == 0:
            return "cache_empty"
        return "gap_in_range"

    def format_line(self, *, idx: int, total: int) -> str:
        tag = _cache_log_tag(self.interval_label)
        cached_span = "-"
        if self.cached_min and self.cached_max:
            cached_span = f"{self.cached_min.isoformat()}..{self.cached_max.isoformat()}"
        ranges_s = ",".join(f"{a.isoformat()}..{b.isoformat()}" for a, b in self.fetch_ranges) or "-"
        bars_hint = ""
        if self.min_bars_per_day > 1:
            bars_hint = f" min_bars/day={self.min_bars_per_day}"
        return (
            f"CACHE | {tag} | [{idx}/{total}] {self.symbol} | "
            f"SELECT days FROM {settings.DB_SCHEMA}.candles_cache "
            f"market=bybit instrument_id={self.symbol} interval={self.interval_label} "
            f"range={self.from_date.isoformat()}..{self.till_date.isoformat()} | "
            f"cached={self.cached_days_count}/{self.expected_days} ({cached_span}) "
            f"missing_raw={self.missing_raw_count} pre_listing_skip={self.pre_listing_skipped_count} "
            f"missing_final={self.missing_final_count}{bars_hint} fetch_ranges={ranges_s} | "
            f"action={self.action} reason={self.reason()}"
        )


@dataclass
class FundingCacheAudit:
    symbol: str
    instrument_category: str
    from_date: date
    till_date: date
    cached_count: int
    min_funding_time: Optional[datetime]
    expected_full: int
    expected_effective: int
    effective_from: datetime
    covers: bool

    @property
    def action(self) -> str:
        return "HIT" if self.covers else "FETCH"

    def reason(self) -> str:
        if self.covers:
            if (
                self.min_funding_time is not None
                and self.effective_from.date() > self.from_date
            ):
                return "pre_listing_gap_ignored"
            return "cache_full"
        if self.cached_count == 0:
            return "cache_empty"
        return "insufficient_slots"

    def format_line(self, *, idx: int, total: int) -> str:
        min_ft_s = self.min_funding_time.isoformat() if self.min_funding_time else "-"
        return (
            f"CACHE | funding | [{idx}/{total}] {self.symbol} | "
            f"SELECT COUNT+MIN FROM bybit_funding_history category={self.instrument_category} "
            f"range={self.from_date.isoformat()}..{self.till_date.isoformat()} | "
            f"cached={self.cached_count} min_ft={min_ft_s} "
            f"expected_full={self.expected_full} expected_effective={self.expected_effective} "
            f"effective_from={self.effective_from.date().isoformat()} | "
            f"action={self.action} reason={self.reason()}"
        )


async def _bybit_rate_limit_pause() -> None:
    global _BYBIT_LAST_REQUEST_AT
    async with _BYBIT_RATE_LOCK:
        now = time_mod.monotonic()
        wait = BYBIT_PUBLIC_API_MIN_INTERVAL_SEC - (now - _BYBIT_LAST_REQUEST_AT)
        if wait > 0:
            await asyncio.sleep(wait)
        _BYBIT_LAST_REQUEST_AT = time_mod.monotonic()

def _to_utc_day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _to_utc_day_end_exclusive(d: date) -> datetime:
    return datetime.combine(d + timedelta(days=1), time.min, tzinfo=timezone.utc)


def _cache_log_tag(interval_label: str) -> str:
    return str(interval_label or "D1").strip().upper() or "D1"


def _expected_bars_per_day(interval_code: int) -> int:
    ic = int(interval_code)
    if ic == 24:
        return 1
    bar_minutes = ic if ic < 24 else 60
    return max(1, (24 * 60) // bar_minutes)


def _min_bars_per_day(interval_code: int) -> int:
    """Crypto 24/7: require ~95% of full intraday bars before treating a day as cached."""
    expected = _expected_bars_per_day(interval_code)
    if expected <= 1:
        return 1
    return max(1, int(expected * 0.95))


def _candles_bar_counts_by_day(
    db: Session,
    *,
    symbol: str,
    interval_label: str,
    from_dt: datetime,
    to_dt_exclusive: datetime,
) -> dict[date, int]:
    rows = db.execute(
        text(
            f"""
            SELECT DATE(candle_time AT TIME ZONE 'UTC') AS d, COUNT(*)::int AS cnt
            FROM {settings.DB_SCHEMA}.candles_cache
            WHERE market = 'bybit'
              AND instrument_id = :symbol
              AND interval = :interval
              AND candle_time >= :from_dt
              AND candle_time < :to_dt_exclusive
            GROUP BY 1
            """
        ),
        {
            "symbol": symbol,
            "interval": interval_label,
            "from_dt": from_dt,
            "to_dt_exclusive": to_dt_exclusive,
        },
    ).fetchall()
    out: dict[date, int] = {}
    for row in rows:
        d_val = row[0]
        cnt = int(row[1] or 0)
        if isinstance(d_val, date):
            out[d_val] = cnt
        elif d_val is not None:
            out[date.fromisoformat(str(d_val)[:10])] = cnt
    return out


def _complete_candle_days_in_range(
    db: Session,
    *,
    symbol: str,
    interval_label: str,
    interval_code: int,
    from_dt: datetime,
    to_dt_exclusive: datetime,
) -> set[date]:
    bar_counts = _candles_bar_counts_by_day(
        db,
        symbol=symbol,
        interval_label=interval_label,
        from_dt=from_dt,
        to_dt_exclusive=to_dt_exclusive,
    )
    min_bars = _min_bars_per_day(interval_code)
    return {d for d, cnt in bar_counts.items() if cnt >= min_bars}


def _merge_contiguous_date_ranges(missing_days: List[date]) -> List[tuple[date, date]]:
    if not missing_days:
        return []
    sorted_days = sorted(missing_days)
    ranges: List[tuple[date, date]] = []
    start = sorted_days[0]
    prev = start
    for d in sorted_days[1:]:
        if d == prev + timedelta(days=1):
            prev = d
            continue
        ranges.append((start, prev))
        start = d
        prev = d
    ranges.append((start, prev))
    return ranges


def _candles_fetch_ranges_for_symbol(
    db: Session,
    *,
    symbol: str,
    interval_label: str,
    from_date: date,
    till_date: date,
    interval_code: int = 24,
) -> List[tuple[date, date]]:
    return _audit_candles_cache_for_symbol(
        db,
        symbol=symbol,
        interval_label=interval_label,
        interval_code=interval_code,
        from_date=from_date,
        till_date=till_date,
    ).fetch_ranges


def _audit_candles_cache_for_symbol(
    db: Session,
    *,
    symbol: str,
    interval_label: str,
    interval_code: int,
    from_date: date,
    till_date: date,
) -> CandlesCacheAudit:
    """Return contiguous date ranges with incomplete candle coverage in candles_cache."""
    from_dt = _to_utc_day_start(from_date)
    to_dt_exclusive = _to_utc_day_end_exclusive(till_date)
    cached_days = _complete_candle_days_in_range(
        db,
        symbol=symbol,
        interval_label=interval_label,
        interval_code=interval_code,
        from_dt=from_dt,
        to_dt_exclusive=to_dt_exclusive,
    )
    min_bars = _min_bars_per_day(interval_code)
    expected_days = max(1, (till_date - from_date).days + 1)
    missing_raw: List[date] = []
    d = from_date
    while d <= till_date:
        if d not in cached_days:
            missing_raw.append(d)
        d += timedelta(days=1)
    pre_listing_skipped = 0
    missing_final = list(missing_raw)
    if cached_days and missing_final:
        first_cached = min(cached_days)
        before = len(missing_final)
        missing_final = [day for day in missing_final if day >= first_cached]
        pre_listing_skipped = before - len(missing_final)
    fetch_ranges = _merge_contiguous_date_ranges(missing_final)
    return CandlesCacheAudit(
        symbol=symbol,
        interval_label=interval_label,
        interval_code=interval_code,
        from_date=from_date,
        till_date=till_date,
        expected_days=expected_days,
        cached_days_count=len(cached_days),
        cached_min=min(cached_days) if cached_days else None,
        cached_max=max(cached_days) if cached_days else None,
        missing_raw_count=len(missing_raw),
        pre_listing_skipped_count=pre_listing_skipped,
        missing_final_count=len(missing_final),
        min_bars_per_day=min_bars,
        fetch_ranges=fetch_ranges,
    )


def _normalize_kline_rows(raw_rows: list) -> list[dict]:
    out: list[dict] = []
    for row in raw_rows:
        if not isinstance(row, list) or len(row) < 7:
            continue
        try:
            out.append(
                {
                    "candle_time": datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        except Exception:
            continue
    return out


BYBIT_KLINE_PAGE_LIMIT = 1000


async def fetch_kline_history(
    client: BybitHttpClient,
    *,
    category: str,
    symbol: str,
    bybit_interval: str,
    from_dt: datetime,
    to_dt_exclusive: datetime,
) -> list[dict]:
    """Paginate Bybit kline API backwards until the requested UTC range is covered."""
    start_ms = int(from_dt.timestamp() * 1000)
    end_ms = int(to_dt_exclusive.timestamp() * 1000)
    cursor_end = end_ms - 1
    merged: dict[int, dict] = {}

    while cursor_end >= start_ms:
        await _bybit_rate_limit_pause()
        data = await client.get_kline(
            category=category,
            symbol=symbol,
            interval=bybit_interval,
            start_ms=start_ms,
            end_ms=cursor_end,
            limit=BYBIT_KLINE_PAGE_LIMIT,
        )
        raw_rows = list((data.get("result") or {}).get("list") or [])
        norm = _normalize_kline_rows(raw_rows)
        if not norm:
            break
        for row in norm:
            ts = int(row["candle_time"].timestamp() * 1000)
            if start_ms <= ts < end_ms:
                merged[ts] = row
        oldest_ms = min(int(row["candle_time"].timestamp() * 1000) for row in norm)
        if oldest_ms <= start_ms or len(norm) < BYBIT_KLINE_PAGE_LIMIT:
            break
        cursor_end = oldest_ms - 1

    return [merged[k] for k in sorted(merged)]


def _upsert_bybit_candles(
    db: Session,
    *,
    symbol: str,
    interval_label: str,
    rows: list[dict],
) -> int:
    if not rows:
        return 0
    wrote = 0
    for r in rows:
        db.execute(
            text(
                f"""
                INSERT INTO {settings.DB_SCHEMA}.candles_cache
                (market, instrument_id, ticker, interval, candle_time, open, high, low, close, volume, source, updated_at)
                VALUES
                ('bybit', :instrument_id, :ticker, :interval, :candle_time, :open, :high, :low, :close, :volume, 'bybit_kline_api', NOW())
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
                "instrument_id": symbol,
                "ticker": symbol,
                "interval": interval_label,
                "candle_time": r["candle_time"],
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": int(r["volume"]),
            },
        )
        wrote += 1
    return wrote


async def ensure_candles_bybit_market(
    db: Session,
    *,
    symbols: Iterable[str],
    resolved: ResolvedInterval,
    from_date: date,
    till_date: date,
    instrument_category: str = "linear",
    testnet: bool = True,
    user_id: Optional[int] = None,
    run_id: Optional[int] = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> CandlePrefetchStats:
    items = sorted({str(s or "").strip().upper() for s in symbols if str(s or "").strip()})
    stats = CandlePrefetchStats(
        total_tickers=len(items),
        interval_label=resolved.cache_label,
        moex_interval_code=0,
    )
    if not items:
        return stats

    bybit_interval = strategy_interval_to_bybit_kline(resolved)

    client = BybitHttpClient(
        testnet=testnet,
        api_key=api_key,
        api_secret=api_secret,
        user_id=user_id,
        context_type="history_backtest_prefetch",
        context_ref=(f"run:{int(run_id)}:candles" if run_id is not None else "candles"),
    )
    category = str(instrument_category or "linear").strip().lower() or "linear"
    cache_tag = _cache_log_tag(resolved.cache_label)
    try:
        from app.modules.robots.trading.backtest.backtest_narrative_log import narrative_sub

        narrative_sub(
            f"Проверка candles_cache: интервал {resolved.cache_label}, символов {len(items)}, "
            f"период {from_date.isoformat()}..{till_date.isoformat()}; "
            f"при нехватке дней — paginated GET /v5/market/kline"
        )
    except Exception:
        pass
    _log_prefetch_cache(
        "CACHE | %s | START symbols=%s interval=%s category=%s range=%s..%s sql=%s",
        cache_tag,
        len(items),
        resolved.cache_label,
        category,
        from_date.isoformat(),
        till_date.isoformat(),
        _CANDLES_DAYS_SQL,
    )
    try:
        for idx, symbol in enumerate(items, start=1):
            if is_cancelled and is_cancelled():
                stats.cancelled = True
                break
            try:
                audit = _audit_candles_cache_for_symbol(
                    db,
                    symbol=symbol,
                    interval_label=resolved.cache_label,
                    interval_code=resolved.code_num,
                    from_date=from_date,
                    till_date=till_date,
                )
                _log_prefetch_cache(audit.format_line(idx=idx, total=stats.total_tickers))
                fetch_ranges = audit.fetch_ranges
                if not fetch_ranges:
                    stats.cache_full_hits += 1
                else:
                    symbol_fetched = False
                    for range_from, range_till in fetch_ranges:
                        range_from_dt = _to_utc_day_start(range_from)
                        range_to_exclusive = _to_utc_day_end_exclusive(range_till)
                        _log_prefetch_cache(
                            "CACHE | %s |     API GET /v5/market/kline symbol=%s category=%s "
                            "interval=%s start=%s end=%s paginated=1",
                            cache_tag,
                            symbol,
                            category,
                            bybit_interval,
                            range_from.isoformat(),
                            range_till.isoformat(),
                        )
                        norm = await fetch_kline_history(
                            client,
                            category=category,
                            symbol=symbol,
                            bybit_interval=bybit_interval,
                            from_dt=range_from_dt,
                            to_dt_exclusive=range_to_exclusive,
                        )
                        wrote = _upsert_bybit_candles(
                            db,
                            symbol=symbol,
                            interval_label=resolved.cache_label,
                            rows=norm,
                        )
                        _log_prefetch_cache(
                            "CACHE | %s |     API result symbol=%s api_rows=%s upserted=%s",
                            cache_tag,
                            symbol,
                            len(norm),
                            wrote,
                        )
                        stats.fetched_ranges += 1
                        stats.fetched_candles += int(wrote)
                        symbol_fetched = symbol_fetched or wrote > 0
                    if symbol_fetched:
                        stats.fetched_tickers += 1
                db.commit()
            except Exception as ex:
                stats.api_errors += 1
                stats.last_api_error = f"{symbol}: {ex}"
                logger.warning(
                    "bybit prefetch symbol=%s idx=%s/%s failed: %s",
                    symbol,
                    idx,
                    stats.total_tickers,
                    ex,
                )
                try:
                    db.rollback()
                except Exception:
                    pass
            stats.processed_tickers = idx
            if run_id is not None:
                touch_backtest_progress_runtime(run_id)
            if progress_callback:
                try:
                    progress_callback(idx, stats.total_tickers)
                except Exception:
                    pass
    finally:
        await client.close()

    logger.info(
        "bybit prefetch interval=%s symbols=%s candles=%s user_id=%s",
        bybit_interval,
        stats.total_tickers,
        stats.fetched_candles,
        user_id,
    )
    return stats


def _expected_funding_slots(from_dt: datetime, to_dt_exclusive: datetime) -> int:
    seconds = max(0.0, (to_dt_exclusive - from_dt).total_seconds())
    return max(1, int(seconds // FUNDING_INTERVAL_SECONDS))


def _funding_cache_covers_range(
    db: Session,
    *,
    symbol: str,
    instrument_category: str,
    from_dt: datetime,
    to_dt_exclusive: datetime,
) -> bool:
    return _audit_funding_cache_for_symbol(
        db,
        symbol=symbol,
        instrument_category=instrument_category,
        from_dt=from_dt,
        to_dt_exclusive=to_dt_exclusive,
    ).covers


def _audit_funding_cache_for_symbol(
    db: Session,
    *,
    symbol: str,
    instrument_category: str,
    from_dt: datetime,
    to_dt_exclusive: datetime,
) -> FundingCacheAudit:
    row = db.execute(
        text(_FUNDING_COVERAGE_SQL),
        {
            "symbol": symbol,
            "instrument_category": instrument_category,
            "from_dt": from_dt,
            "to_dt_exclusive": to_dt_exclusive,
        },
    ).mappings().first()
    actual = int((row or {}).get("cnt") or 0)
    min_ft = (row or {}).get("min_ft")
    min_ft_utc: Optional[datetime] = None
    if min_ft is not None:
        if isinstance(min_ft, datetime):
            min_ft_utc = min_ft.astimezone(timezone.utc) if min_ft.tzinfo else min_ft.replace(tzinfo=timezone.utc)
        else:
            min_ft_utc = datetime.fromisoformat(str(min_ft).replace("Z", "+00:00"))
            if min_ft_utc.tzinfo is None:
                min_ft_utc = min_ft_utc.replace(tzinfo=timezone.utc)
    effective_from = from_dt
    if min_ft_utc is not None and min_ft_utc > effective_from:
        effective_from = min_ft_utc
    expected_full = _expected_funding_slots(from_dt, to_dt_exclusive)
    expected_effective = _expected_funding_slots(effective_from, to_dt_exclusive)
    covers = actual > 0 and actual >= max(1, expected_effective - 1)
    return FundingCacheAudit(
        symbol=symbol,
        instrument_category=instrument_category,
        from_date=from_dt.date(),
        till_date=(to_dt_exclusive - timedelta(days=1)).date(),
        cached_count=actual,
        min_funding_time=min_ft_utc,
        expected_full=expected_full,
        expected_effective=expected_effective,
        effective_from=effective_from,
        covers=covers,
    )


def _normalize_funding_rows(raw_rows: list) -> list[dict]:
    out: list[dict] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        try:
            out.append(
                {
                    "funding_time": datetime.fromtimestamp(
                        int(row.get("fundingRateTimestamp") or 0) / 1000,
                        tz=timezone.utc,
                    ),
                    "funding_rate": float(row.get("fundingRate") or 0),
                }
            )
        except Exception:
            continue
    return out


def _upsert_funding_rows(
    db: Session,
    *,
    symbol: str,
    instrument_category: str,
    rows: list[dict],
) -> int:
    if not rows:
        return 0
    wrote = 0
    for r in rows:
        db.execute(
            text(
                f"""
                INSERT INTO {settings.DB_SCHEMA}.bybit_funding_history
                (symbol, funding_time, funding_rate, instrument_category, created_at)
                VALUES
                (:symbol, :funding_time, :funding_rate, :instrument_category, NOW())
                ON CONFLICT (symbol, funding_time, instrument_category)
                DO NOTHING
                """
            ),
            {
                "symbol": symbol,
                "funding_time": r["funding_time"],
                "funding_rate": r["funding_rate"],
                "instrument_category": instrument_category,
            },
        )
        wrote += 1
    return wrote


async def fetch_funding_history(
    client: BybitHttpClient,
    *,
    category: str,
    symbol: str,
    from_dt: datetime,
    to_dt_exclusive: datetime,
) -> list[dict]:
    start_ms = int(from_dt.timestamp() * 1000)
    end_ms = int(to_dt_exclusive.timestamp() * 1000)
    cursor_end = end_ms
    merged: dict[int, dict] = {}

    while cursor_end > start_ms:
        await _bybit_rate_limit_pause()
        data = await client.get_funding_history(
            category=category,
            symbol=symbol,
            start_ms=start_ms,
            end_ms=cursor_end,
            limit=200,
        )
        raw_rows = list((data.get("result") or {}).get("list") or [])
        norm = _normalize_funding_rows(raw_rows)
        if not norm:
            break
        for row in norm:
            ts = int(row["funding_time"].timestamp() * 1000)
            merged[ts] = row
        oldest_ms = min(int(row["funding_time"].timestamp() * 1000) for row in norm)
        if oldest_ms <= start_ms or len(norm) < 200:
            break
        cursor_end = oldest_ms - 1

    return [merged[k] for k in sorted(merged)]


async def ensure_funding_bybit_market(
    db: Session,
    *,
    symbols: Iterable[str],
    from_date: date,
    till_date: date,
    instrument_category: str = "linear",
    testnet: bool = True,
    user_id: Optional[int] = None,
    run_id: Optional[int] = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> FundingPrefetchStats:
    if instrument_category == "spot":
        return FundingPrefetchStats()

    items = sorted({str(s or "").strip().upper() for s in symbols if str(s or "").strip()})
    stats = FundingPrefetchStats(total_symbols=len(items))
    if not items:
        return stats

    from_dt = _to_utc_day_start(from_date)
    to_dt_exclusive = _to_utc_day_end_exclusive(till_date)
    client = BybitHttpClient(
        testnet=testnet,
        api_key=api_key,
        api_secret=api_secret,
        user_id=user_id,
        context_type="history_backtest_prefetch",
        context_ref=(f"run:{int(run_id)}:funding" if run_id is not None else "funding"),
    )
    try:
        from app.modules.robots.trading.backtest.backtest_narrative_log import narrative_sub

        narrative_sub(
            f"Проверка bybit_funding_history: символов {len(items)}, "
            f"период {from_date.isoformat()}..{till_date.isoformat()}; "
            f"при нехватке — GET /v5/market/funding/history"
        )
    except Exception:
        pass
    _log_prefetch_cache(
        "CACHE | funding | START symbols=%s category=%s range=%s..%s sql=%s",
        len(items),
        instrument_category,
        from_date.isoformat(),
        till_date.isoformat(),
        _FUNDING_COVERAGE_SQL,
    )
    try:
        for idx, symbol in enumerate(items, start=1):
            if is_cancelled and is_cancelled():
                stats.cancelled = True
                break
            try:
                audit = _audit_funding_cache_for_symbol(
                    db,
                    symbol=symbol,
                    instrument_category=instrument_category,
                    from_dt=from_dt,
                    to_dt_exclusive=to_dt_exclusive,
                )
                _log_prefetch_cache(audit.format_line(idx=idx, total=stats.total_symbols))
                if audit.covers:
                    stats.cache_full_hits += 1
                else:
                    _log_prefetch_cache(
                        "CACHE | funding |     API GET /v5/market/funding/history symbol=%s "
                        "category=%s start=%s end=%s",
                        symbol,
                        instrument_category,
                        from_dt.date().isoformat(),
                        (to_dt_exclusive - timedelta(days=1)).date().isoformat(),
                    )
                    rows = await fetch_funding_history(
                        client,
                        category=instrument_category,
                        symbol=symbol,
                        from_dt=from_dt,
                        to_dt_exclusive=to_dt_exclusive,
                    )
                    wrote = _upsert_funding_rows(
                        db,
                        symbol=symbol,
                        instrument_category=instrument_category,
                        rows=rows,
                    )
                    _log_prefetch_cache(
                        "CACHE | funding |     API result symbol=%s api_rows=%s upserted=%s",
                        symbol,
                        len(rows),
                        wrote,
                    )
                    stats.fetched_symbols += 1
                    stats.fetched_rows += int(wrote)
                db.commit()
            except Exception as ex:
                stats.api_errors += 1
                stats.last_api_error = f"{symbol}: {ex}"
                logger.warning(
                    "bybit funding prefetch symbol=%s idx=%s/%s failed: %s",
                    symbol,
                    idx,
                    stats.total_symbols,
                    ex,
                )
                try:
                    db.rollback()
                except Exception:
                    pass
            stats.processed_symbols = idx
            if run_id is not None:
                touch_backtest_progress_runtime(run_id)
            if progress_callback:
                try:
                    progress_callback(idx, stats.total_symbols)
                except Exception:
                    pass
    finally:
        await client.close()

    logger.info(
        "bybit funding prefetch category=%s symbols=%s rows=%s user_id=%s",
        instrument_category,
        stats.total_symbols,
        stats.fetched_rows,
        user_id,
    )
    return stats


def load_funding_history_from_cache(
    db: Session,
    *,
    symbols: Iterable[str],
    instrument_category: str,
    from_dt: datetime,
    to_dt_exclusive: datetime,
) -> dict[str, list[dict]]:
    """Read prefetched funding rows for backtest replay."""
    items = sorted({str(s or "").strip().upper() for s in symbols if str(s or "").strip()})
    out: dict[str, list[dict]] = {}
    if not items:
        return out
    for symbol in items:
        rows = (
            db.execute(
                text(
                    f"""
                    SELECT funding_time, funding_rate
                    FROM {settings.DB_SCHEMA}.bybit_funding_history
                    WHERE symbol = :symbol
                      AND instrument_category = :instrument_category
                      AND funding_time >= :from_dt
                      AND funding_time < :to_dt_exclusive
                    ORDER BY funding_time ASC
                    """
                ),
                {
                    "symbol": symbol,
                    "instrument_category": instrument_category,
                    "from_dt": from_dt,
                    "to_dt_exclusive": to_dt_exclusive,
                },
            )
            .mappings()
            .all()
        )
        if rows:
            out[symbol] = [
                {
                    "funding_time": r["funding_time"],
                    "funding_rate": float(r["funding_rate"] or 0),
                }
                for r in rows
            ]
    return out


def screening_d1_prefetch_range(
    trade_dates: Iterable[date],
    config: dict[str, Any],
) -> tuple[date, date]:
    """Date range for D1 candles needed by crypto universe screening (no look-ahead)."""
    from app.modules.robots.crypto_universe import resolve_crypto_universe_filters
    from app.modules.robots.trading.pipeline.historical_liquidity import volume_lookback_days

    dates = list(trade_dates)
    if not dates:
        today = datetime.now(timezone.utc).date()
        return today - timedelta(days=30), today

    filters = resolve_crypto_universe_filters(config)
    lookback = max(filters.lookback_days, volume_lookback_days(config, default=filters.lookback_days))
    buffer_days = max(5, int(filters.atr_period) + 2)

    min_td = min(dates)
    max_td = max(dates)
    from_date = min_td - timedelta(days=lookback + buffer_days)
    till_date = max_td - timedelta(days=1)
    if till_date < from_date:
        till_date = from_date
    return from_date, till_date


async def resolve_crypto_screening_symbols(
    db: Session,
    *,
    config: dict[str, Any],
    allowed_tickers_whitelist: Optional[Set[str]] = None,
    testnet: bool = True,
    prefer_live_universe: bool = False,
    user_id: Optional[int] = None,
    run_id: Optional[int] = None,
) -> List[str]:
    """
    Symbol pool for crypto screening: explicit config → whitelist → live API / cache.

    When ``prefer_live_universe`` is set (backtest prefetch), instruments are fetched
    from ByBit at run start. For ``linear`` only ``LinearPerpetual`` contracts are kept
    (dated futures like ``DOGEUSDT-26JUN26`` are excluded). Cache is only a fallback
    if the API call fails.
    """
    from app.modules.bybit.instruments import list_instruments
    from app.modules.robots.trading.pipeline.bybit_symbol_filter import filter_backtest_universe_symbols
    from app.modules.robots.trading.pipeline.historical_liquidity import list_bybit_symbols_from_cache
    from app.modules.robots.universe import resolve_crypto_symbols

    explicit = resolve_crypto_symbols(config)
    if explicit:
        return filter_backtest_universe_symbols(explicit)
    if allowed_tickers_whitelist:
        return filter_backtest_universe_symbols(
            {str(s).strip().upper() for s in allowed_tickers_whitelist if str(s).strip()}
        )

    bybit = config.get("bybit") if isinstance(config.get("bybit"), dict) else {}
    category = str(bybit.get("instrument_category") or "linear").strip().lower() or "linear"

    async def _from_api() -> List[str]:
        from app.modules.robots.trading.backtest.backtest_narrative_log import narrative_sub

        narrative_sub(
            f"Запрос к ByBit: GET /v5/market/instruments-info "
            f"(category={category}, quoteCoin=USDT)"
        )
        instruments = await list_instruments(
            category=category,  # type: ignore[arg-type]
            quote_coin="USDT",
            testnet=testnet,
            user_id=user_id,
            context_type="history_backtest_prefetch",
            context_ref=(f"run:{int(run_id)}:instruments" if run_id is not None else "instruments"),
        )
        _log_prefetch_cache(
            "CACHE | symbols | API GET /v5/market/instruments-info category=%s quoteCoin=USDT "
            "returned=%s",
            category,
            len(instruments),
        )
        out: List[str] = []
        skipped_contract_type = 0
        for r in instruments:
            symbol = str(r.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            if category == "linear":
                contract_type = str(r.get("contract_type") or "").strip()
                if contract_type and contract_type != "LinearPerpetual":
                    skipped_contract_type += 1
                    continue
            out.append(symbol)
        filtered = filter_backtest_universe_symbols(out)
        narrative_sub(
            f"Ответ ByBit: инструментов {len(instruments)}, perpetual USDT {len(out)}, "
            f"пропущено по contract_type {skipped_contract_type}, "
            f"после фильтра датированных контрактов {len(filtered)}"
        )
        _log_prefetch_cache(
            "CACHE | symbols | filter perpetual_only=%s skipped_contract_type=%s "
            "after_dated_filter=%s",
            category == "linear",
            skipped_contract_type,
            len(filtered),
        )
        return filtered

    if prefer_live_universe:
        try:
            live = await _from_api()
            if live:
                _log_prefetch_cache(
                    "CACHE | symbols | source=live_api count=%s",
                    len(live),
                )
                return sorted(set(live))
        except Exception as ex:
            logger.warning("crypto screening symbols: live instruments failed: %s", ex)
            _log_prefetch_cache("CACHE | symbols | source=live_api FAILED error=%s", ex)
        cached = list_bybit_symbols_from_cache(db)
        if cached:
            logger.warning(
                "crypto screening symbols: using cache fallback (%s symbols) after API failure",
                len(cached),
            )
            filtered_cached = filter_backtest_universe_symbols(cached)
            _log_prefetch_cache(
                "CACHE | symbols | source=candles_cache_fallback sql=DISTINCT instrument_id "
                "FROM candles_cache market=bybit raw=%s after_dated_filter=%s",
                len(cached),
                len(filtered_cached),
            )
            return filtered_cached
        return []

    cached = list_bybit_symbols_from_cache(db)
    if cached:
        return filter_backtest_universe_symbols(cached)
    return await _from_api()


async def ensure_crypto_screening_d1_candles(
    db: Session,
    *,
    trade_dates: Iterable[date],
    config: dict[str, Any],
    allowed_tickers_whitelist: Optional[Set[str]] = None,
    symbols: Optional[List[str]] = None,
    testnet: bool = True,
    user_id: Optional[int] = None,
    run_id: Optional[int] = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    prefer_live_universe: bool = False,
) -> CandlePrefetchStats:
    """
    Ensure D1 candles in candles_cache for crypto universe screening before scoring.

    Resolves symbol list from live ByBit instruments when ``prefer_live_universe``;
    for each symbol checks cache day-by-day and fetches only missing dates via API.
    """
    from app.modules.robots.trading.intervals import resolve_strategy_interval

    dates = list(trade_dates)
    if symbols is None:
        symbols = await resolve_crypto_screening_symbols(
            db,
            config=config,
            allowed_tickers_whitelist=allowed_tickers_whitelist,
            testnet=testnet,
            prefer_live_universe=prefer_live_universe,
            user_id=user_id,
            run_id=run_id,
        )
    if not symbols:
        logger.warning("crypto screening D1 prefetch: no symbols resolved")
        return CandlePrefetchStats(interval_label="D1")

    from_date, till_date = screening_d1_prefetch_range(dates, config)
    _log_prefetch_cache(
        "CACHE | D1 | RANGE trade_dates=%s..%s prefetch_range=%s..%s "
        "(lookback from crypto_universe + ATR buffer, till=max_trade_date-1)",
        dates[0].isoformat() if dates else "-",
        dates[-1].isoformat() if dates else "-",
        from_date.isoformat(),
        till_date.isoformat(),
    )
    bybit = config.get("bybit") if isinstance(config.get("bybit"), dict) else {}
    instrument_category = str(bybit.get("instrument_category") or "linear").strip().lower() or "linear"
    resolved_d1 = resolve_strategy_interval("CANDLE_INTERVAL_DAY")

    stats = await ensure_candles_bybit_market(
        db,
        symbols=symbols,
        resolved=resolved_d1,
        from_date=from_date,
        till_date=till_date,
        instrument_category=instrument_category,
        testnet=testnet,
        user_id=user_id,
        run_id=run_id,
        api_key=api_key,
        api_secret=api_secret,
        is_cancelled=is_cancelled,
        progress_callback=progress_callback,
    )
    logger.info(
        "crypto screening D1 prefetch from=%s till=%s symbols=%s %s",
        from_date.isoformat(),
        till_date.isoformat(),
        stats.total_tickers,
        stats.summary(),
    )
    return stats


async def ensure_crypto_screening_funding_history(
    db: Session,
    *,
    trade_dates: Iterable[date],
    config: dict[str, Any],
    allowed_tickers_whitelist: Optional[Set[str]] = None,
    symbols: Optional[List[str]] = None,
    user_id: Optional[int] = None,
    run_id: Optional[int] = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    prefer_live_universe: bool = False,
) -> FundingPrefetchStats:
    """
    Ensure funding history in bybit_funding_history before crypto universe scoring.

    Uses the same symbol pool and date range as D1 screening prefetch.
    """
    dates = list(trade_dates)
    if symbols is None:
        symbols = await resolve_crypto_screening_symbols(
            db,
            config=config,
            allowed_tickers_whitelist=allowed_tickers_whitelist,
            prefer_live_universe=prefer_live_universe,
            user_id=user_id,
            run_id=run_id,
        )
    if not symbols:
        logger.warning("crypto screening funding prefetch: no symbols resolved")
        return FundingPrefetchStats()

    from_date, till_date = screening_d1_prefetch_range(dates, config)
    _log_prefetch_cache(
        "CACHE | D1 | RANGE trade_dates=%s..%s prefetch_range=%s..%s "
        "(lookback from crypto_universe + ATR buffer, till=max_trade_date-1)",
        dates[0].isoformat() if dates else "-",
        dates[-1].isoformat() if dates else "-",
        from_date.isoformat(),
        till_date.isoformat(),
    )
    bybit = config.get("bybit") if isinstance(config.get("bybit"), dict) else {}
    instrument_category = str(bybit.get("instrument_category") or "linear").strip().lower() or "linear"
    if instrument_category == "spot":
        return FundingPrefetchStats()

    stats = await ensure_funding_bybit_market(
        db,
        symbols=symbols,
        from_date=from_date,
        till_date=till_date,
        instrument_category=instrument_category,
        user_id=user_id,
        run_id=run_id,
        api_key=api_key,
        api_secret=api_secret,
        is_cancelled=is_cancelled,
        progress_callback=progress_callback,
    )
    logger.info(
        "crypto screening funding prefetch from=%s till=%s symbols=%s %s",
        from_date.isoformat(),
        till_date.isoformat(),
        stats.total_symbols,
        stats.summary(),
    )
    return stats


__all__ = [
    "ensure_candles_bybit_market",
    "ensure_crypto_screening_d1_candles",
    "ensure_crypto_screening_funding_history",
    "ensure_funding_bybit_market",
    "fetch_funding_history",
    "fetch_kline_history",
    "load_funding_history_from_cache",
    "resolve_crypto_screening_symbols",
    "screening_d1_prefetch_range",
]