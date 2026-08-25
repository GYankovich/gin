"""Crypto universe screening for ByBit symbols (R5.1 + extended filters)."""

from __future__ import annotations

import asyncio
import copy
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.modules.bybit.http_client import BybitHttpClient
from app.modules.robots.crypto_universe_metrics import (
    avg_funding_rate,
    compute_atr_percent,
    compute_lsr,
    compute_rvol,
    open_interest_usd,
    passes_atr_percent,
    passes_funding_range,
    passes_lsr,
    passes_oi,
    passes_rvol,
)

logger = get_logger(__name__)

# OI/LSR ByBit endpoints are 5m granularity; reuse DB snapshots within this TTL.
DERIVATIVE_SNAPSHOT_TTL_MINUTES = 15
# Funding prints ~every 8h on linear; require a point at least this fresh for cache hit.
FUNDING_CACHE_MAX_AGE_HOURS = 8
# Commit ByBit derivative cache every N symbols with API writes (survive worker kill).
DERIVATIVE_CACHE_COMMIT_EVERY = 1


@dataclass
class CryptoUniverseFilters:
    min_turnover_24h_usd: float = 50_000_000.0
    max_spread_pct: float = 0.15
    """Maximum bid-ask spread in percent (15 bps in UI → 0.15 here)."""
    min_last_price: float = 0.05
    limit: int = 80
    category: str = "linear"
    quote_coin: str = "USDT"
    min_funding_rate: Optional[float] = -0.0001
    max_funding_rate: Optional[float] = 0.0002
    funding_lookback_hours: int = 8
    min_open_interest_usd: Optional[float] = 20_000_000.0
    min_lsr: Optional[float] = 0.5
    max_lsr: Optional[float] = 1.5
    min_rvol: Optional[float] = 2.0
    min_atr_percent: Optional[float] = 1.5
    max_atr_percent: Optional[float] = 10.0
    lookback_days: int = 20
    atr_period: int = 14


@dataclass
class ScreeningRow:
    symbol: str
    turnover24h: float
    lastPrice: float
    spreadPercent: Optional[float] = None
    """Bid-ask spread in percent (e.g. 0.05 = 0.05%). Used for live screening filter."""
    dailyRangePercent: Optional[float] = None
    """D1 (high-low)/close in percent — backtest context only, not compared to max_spread."""
    score: float = 0.0
    avg_funding_rate: Optional[float] = None
    open_interest_usd: Optional[float] = None
    lsr: Optional[float] = None
    long_ratio: Optional[float] = None
    short_ratio: Optional[float] = None
    rvol: Optional[float] = None
    atr_percent: Optional[float] = None
    filter_result: str = "accepted"
    reject_reason: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _spread_percent(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return None
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return None
    return abs(ask - bid) / mid * 100.0


def _liquidity_score(turnover: float, spread_pct: float) -> float:
    return turnover / max(spread_pct, 0.001)


def apply_basic_filters(
    tickers: Iterable[Dict[str, Any]],
    *,
    filters: CryptoUniverseFilters,
) -> Tuple[List[ScreeningRow], List[ScreeningRow]]:
    """
    Basic liquidity filters. Spread filter uses bid-ask % only (live).

    Historical backtest rows may include ``dailyRangePercent`` (D1 range); that metric
    is stored for logs but is not compared to ``max_spread_pct``.
    """
    accepted: List[ScreeningRow] = []
    rejected: List[ScreeningRow] = []
    max_spread_pct = float(filters.max_spread_pct)
    for t in tickers:
        symbol = str(t.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        if filters.quote_coin and not symbol.endswith(filters.quote_coin.upper()):
            continue
        turnover = _safe_float(t.get("turnover24h"))
        last_price = _safe_float(t.get("lastPrice"))
        bid = _safe_float(t.get("bid1Price"))
        ask = _safe_float(t.get("ask1Price"))
        spread_pct = _spread_percent(bid, ask)
        if spread_pct is None:
            spread_pct = _safe_float(t.get("spreadPercent"))
        daily_range_pct = _safe_float(t.get("dailyRangePercent"))

        row = ScreeningRow(
            symbol=symbol,
            turnover24h=float(turnover or 0),
            lastPrice=float(last_price or 0),
            spreadPercent=spread_pct,
            dailyRangePercent=daily_range_pct,
        )
        if turnover is None or turnover < float(filters.min_turnover_24h_usd):
            row.filter_result = "rejected"
            row.reject_reason = "volume_below_min"
            rejected.append(row)
            continue
        min_price = float(filters.min_last_price)
        if min_price > 0 and (last_price is None or last_price < min_price):
            row.filter_result = "rejected"
            row.reject_reason = "price_below_min"
            rejected.append(row)
            continue
        has_bid_ask = bid is not None and ask is not None and bid > 0 and ask > 0
        if has_bid_ask or spread_pct is not None:
            if spread_pct is None:
                row.filter_result = "rejected"
                row.reject_reason = "spread_missing"
                rejected.append(row)
                continue
            if spread_pct > max_spread_pct:
                row.filter_result = "rejected"
                row.reject_reason = "spread_above_max"
                rejected.append(row)
                continue
        score_spread = spread_pct if spread_pct is not None else daily_range_pct
        row.score = _liquidity_score(turnover, float(score_spread or 0.001))
        accepted.append(row)
    accepted.sort(key=lambda x: x.score, reverse=True)
    return accepted, rejected


def score_bybit_tickers(
    tickers: Iterable[Dict[str, Any]],
    *,
    filters: CryptoUniverseFilters,
) -> List[Dict[str, Any]]:
    """Legacy entry: basic filters only (backward compatible)."""
    accepted, _ = apply_basic_filters(tickers, filters=filters)
    capped = accepted[: max(1, int(filters.limit))]
    return [
        {
            "symbol": r.symbol,
            "turnover24h": r.turnover24h,
            "lastPrice": r.lastPrice,
            "spreadPercent": r.spreadPercent,
            "score": r.score,
        }
        for r in capped
    ]


def _derivative_filters_enabled(filters: CryptoUniverseFilters) -> bool:
    return any(
        v is not None
        for v in (
            filters.min_funding_rate,
            filters.max_funding_rate,
            filters.min_open_interest_usd,
            filters.min_lsr,
            filters.max_lsr,
        )
    )


def _volatility_filters_enabled(filters: CryptoUniverseFilters) -> bool:
    return any(
        v is not None
        for v in (filters.min_rvol, filters.min_atr_percent, filters.max_atr_percent)
    )


def _ms_to_utc(ms: Any) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
    except Exception:
        return None


def _bulk_load_funding_avg_from_cache(
    db: Session,
    *,
    symbols: List[str],
    category: str,
    lookback_hours: int,
    now: Optional[datetime] = None,
) -> Dict[str, float]:
    """Avg funding from DB when the latest print is fresh enough."""
    if not symbols:
        return {}
    now_utc = now or datetime.now(timezone.utc)
    from_dt = now_utc - timedelta(hours=max(1, int(lookback_hours)))
    fresh_after = now_utc - timedelta(hours=max(1, int(FUNDING_CACHE_MAX_AGE_HOURS)))
    rows = db.execute(
        text(
            f"""
            SELECT symbol, funding_rate, funding_time
            FROM bybit_funding_history
            WHERE symbol = ANY(:symbols)
              AND instrument_category = :category
              AND funding_time >= :from_dt
              AND funding_time <= :now_utc
            ORDER BY symbol, funding_time
            """
        ),
        {
            "symbols": [s.upper() for s in symbols],
            "category": category,
            "from_dt": from_dt,
            "now_utc": now_utc,
        },
    ).fetchall()
    by_sym: Dict[str, List[Tuple[float, datetime]]] = {}
    for symbol, rate, ts in rows:
        r = _safe_float(rate)
        if r is None or ts is None:
            continue
        t = ts if getattr(ts, "tzinfo", None) else ts.replace(tzinfo=timezone.utc)
        by_sym.setdefault(str(symbol).upper(), []).append((r, t))
    out: Dict[str, float] = {}
    for symbol, points in by_sym.items():
        latest = max(t for _, t in points)
        if latest < fresh_after:
            continue
        avg = avg_funding_rate([{"funding_rate": r} for r, _ in points])
        if avg is not None:
            out[symbol] = float(avg)
    return out


def _bulk_load_oi_from_cache(
    db: Session,
    *,
    symbols: List[str],
    category: str,
    ttl_minutes: int = DERIVATIVE_SNAPSHOT_TTL_MINUTES,
    now: Optional[datetime] = None,
) -> Dict[str, float]:
    if not symbols:
        return {}
    now_utc = now or datetime.now(timezone.utc)
    min_ts = now_utc - timedelta(minutes=max(1, int(ttl_minutes)))
    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT ON (symbol)
                symbol, open_interest_usd
            FROM bybit_open_interest_history
            WHERE symbol = ANY(:symbols)
              AND instrument_category = :category
              AND snapshot_time >= :min_ts
              AND snapshot_time <= :now_utc
            ORDER BY symbol, snapshot_time DESC
            """
        ),
        {
            "symbols": [s.upper() for s in symbols],
            "category": category,
            "min_ts": min_ts,
            "now_utc": now_utc,
        },
    ).fetchall()
    out: Dict[str, float] = {}
    for symbol, oi in rows:
        v = _safe_float(oi)
        if v is not None:
            out[str(symbol).upper()] = float(v)
    return out


def _bulk_load_lsr_from_cache(
    db: Session,
    *,
    symbols: List[str],
    category: str,
    ttl_minutes: int = DERIVATIVE_SNAPSHOT_TTL_MINUTES,
    now: Optional[datetime] = None,
) -> Dict[str, Tuple[float, float, float]]:
    """symbol → (lsr, long_ratio, short_ratio)."""
    if not symbols:
        return {}
    now_utc = now or datetime.now(timezone.utc)
    min_ts = now_utc - timedelta(minutes=max(1, int(ttl_minutes)))
    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT ON (symbol)
                symbol, long_ratio, short_ratio
            FROM bybit_lsr_history
            WHERE symbol = ANY(:symbols)
              AND instrument_category = :category
              AND snapshot_time >= :min_ts
              AND snapshot_time <= :now_utc
            ORDER BY symbol, snapshot_time DESC
            """
        ),
        {
            "symbols": [s.upper() for s in symbols],
            "category": category,
            "min_ts": min_ts,
            "now_utc": now_utc,
        },
    ).fetchall()
    out: Dict[str, Tuple[float, float, float]] = {}
    for symbol, long_r, short_r in rows:
        buy = _safe_float(long_r)
        sell = _safe_float(short_r)
        if buy is None or sell is None:
            continue
        lsr = compute_lsr(buy, sell)
        if lsr is None:
            continue
        out[str(symbol).upper()] = (float(lsr), float(buy), float(sell))
    return out


def _persist_funding_history_rows(
    db: Session,
    *,
    symbol: str,
    category: str,
    rows: List[Dict[str, Any]],
) -> None:
    for r in rows:
        ts = r.get("funding_time")
        rate = _safe_float(r.get("funding_rate"))
        if ts is None or rate is None:
            continue
        db.execute(
            text(
                f"""
                INSERT INTO bybit_funding_history
                (symbol, funding_time, funding_rate, instrument_category, created_at)
                VALUES (:symbol, :funding_time, :funding_rate, :category, NOW())
                ON CONFLICT (symbol, funding_time, instrument_category) DO NOTHING
                """
            ),
            {
                "symbol": symbol.upper(),
                "funding_time": ts,
                "funding_rate": rate,
                "category": category,
            },
        )


def _commit_derivative_cache(db: Session) -> bool:
    """Persist market-cache writes so a mid-screening kill does not lose them."""
    try:
        db.commit()
        return True
    except Exception as exc:
        logger.warning("screening market cache commit failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return False


def _kline_raw_to_cache_rows(raw_rows: List[Any]) -> List[Dict[str, Any]]:
    """ByBit kline list → candles_cache upsert dicts (accepts 6+ fields)."""
    out: List[Dict[str, Any]] = []
    for item in raw_rows:
        if not isinstance(item, (list, tuple)) or len(item) < 6:
            continue
        try:
            ts_ms = int(item[0])
            open_ = float(item[1])
            high = float(item[2])
            low = float(item[3])
            close = float(item[4])
            vol = float(item[5])
        except Exception:
            continue
        if close <= 0:
            continue
        out.append(
            {
                "candle_time": datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": vol,
            }
        )
    return out


async def _fetch_avg_funding_live(
    client: BybitHttpClient,
    *,
    category: str,
    symbol: str,
    lookback_hours: int,
) -> Tuple[Optional[float], List[Dict[str, Any]]]:
    """Returns (avg_rate, raw rows for cache upsert)."""
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - int(lookback_hours) * 3600 * 1000
    raw: List[Dict[str, Any]] = []
    try:
        data = await client.get_funding_history(
            category=category,
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=50,
        )
        rows = list((data.get("result") or {}).get("list") or [])
        for r in rows:
            rate = _safe_float(r.get("fundingRate"))
            ts = _ms_to_utc(r.get("fundingRateTimestamp") or r.get("fundingTime"))
            if rate is None or ts is None:
                continue
            raw.append({"funding_rate": rate, "funding_time": ts})
        avg = avg_funding_rate([{"funding_rate": x["funding_rate"]} for x in raw])
        if avg is not None:
            return avg, raw
    except Exception:
        pass
    try:
        data = await client.get_tickers(category=category, symbol=symbol)
        rows = list((data.get("result") or {}).get("list") or [])
        if rows:
            return _safe_float(rows[0].get("fundingRate")), raw
    except Exception:
        pass
    return None, raw


async def _fetch_open_interest_usd_live(
    client: BybitHttpClient,
    *,
    category: str,
    symbol: str,
    last_price: float,
) -> Optional[float]:
    try:
        data = await client.get_open_interest(
            category=category,
            symbol=symbol,
            interval_time="5min",
            limit=1,
        )
        rows = list((data.get("result") or {}).get("list") or [])
        if not rows:
            return None
        oi_base = _safe_float(rows[0].get("openInterest"))
        mark = _safe_float(rows[0].get("markPrice")) or last_price
        return open_interest_usd(float(oi_base or 0), float(mark or 0))
    except Exception:
        return None


async def _fetch_lsr_live(
    client: BybitHttpClient,
    *,
    category: str,
    symbol: str,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    try:
        data = await client.get_account_ratio(
            category=category,
            symbol=symbol,
            period="5min",
            limit=1,
        )
        rows = list((data.get("result") or {}).get("list") or [])
        if not rows:
            return None, None, None
        buy = _safe_float(rows[0].get("buyRatio"))
        sell = _safe_float(rows[0].get("sellRatio"))
        if buy is None or sell is None:
            return None, None, None
        return compute_lsr(buy, sell), buy, sell
    except Exception:
        return None, None, None


def _parse_kline_rows(raw_rows: List[Any]) -> Tuple[List[float], List[float], List[float], List[float]]:
    """ByBit kline list is [start, open, high, low, close, volume, turnover]."""
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    volumes: List[float] = []
    for item in raw_rows:
        if not isinstance(item, (list, tuple)) or len(item) < 6:
            continue
        high = _safe_float(item[2])
        low = _safe_float(item[3])
        close = _safe_float(item[4])
        vol = _safe_float(item[5])
        if close is None or close <= 0:
            continue
        highs.append(float(high or close))
        lows.append(float(low or close))
        closes.append(float(close))
        volumes.append(float(vol or 0))
    return highs, lows, closes, volumes


def _ohlcv_from_cache_rows(
    rows: List[Any],
) -> Tuple[List[float], List[float], List[float], List[float]]:
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    volumes: List[float] = []
    for row in rows:
        if hasattr(row, "get"):
            high = _safe_float(row.get("high"))
            low = _safe_float(row.get("low"))
            close = _safe_float(row.get("close"))
            vol = _safe_float(row.get("volume"))
        else:
            continue
        if close is None or close <= 0:
            continue
        highs.append(float(high or close))
        lows.append(float(low or close))
        closes.append(float(close))
        volumes.append(float(vol or 0))
    return highs, lows, closes, volumes


def _volatility_from_ohlcv(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    *,
    atr_period: int,
) -> Tuple[Optional[float], Optional[float]]:
    rvol = compute_rvol(volumes)
    atr_pct = compute_atr_percent(highs, lows, closes, period=atr_period)
    return rvol, atr_pct


def _bulk_load_volatility_from_candles_cache(
    db: Session,
    *,
    symbols: List[str],
    lookback_days: int,
    atr_period: int,
    now: Optional[datetime] = None,
) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """symbol → (rvol, atr_percent) from bybit D1 candles_cache when enough bars exist."""
    if not symbols:
        return {}
    from app.modules.robots.trading.data.providers.db_cache import query_candles_cache_rows_bulk

    now_utc = now or datetime.now(timezone.utc)
    # Inclusive of today's D1 bar if present; exclusive end = tomorrow UTC midnight.
    end = datetime(
        now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc
    ) + timedelta(days=1)
    need = max(int(lookback_days) + 1, int(atr_period) + 2)
    start = end - timedelta(days=need + 3)
    try:
        grouped = query_candles_cache_rows_bulk(
            db,
            market="bybit",
            instrument_ids=symbols,
            interval_code="D1",
            interval_code_num=24,
            from_dt=start,
            to_dt_exclusive=end,
        )
    except Exception as exc:
        logger.warning("volatility candles_cache bulk load failed: %s", exc)
        return {}

    out: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    min_bars = max(2, int(atr_period) + 1)
    for sym, rows in grouped.items():
        if not rows or len(rows) < min_bars:
            continue
        highs, lows, closes, volumes = _ohlcv_from_cache_rows(list(rows))
        if len(closes) < min_bars:
            continue
        rvol, atr_pct = _volatility_from_ohlcv(
            highs, lows, closes, volumes, atr_period=atr_period
        )
        # Accept cache hit when at least one metric is computable; prefer both.
        if rvol is None and atr_pct is None:
            continue
        out[str(sym).upper()] = (rvol, atr_pct)
    return out


async def _fetch_volatility_metrics_live(
    client: BybitHttpClient,
    *,
    category: str,
    symbol: str,
    lookback_days: int,
    atr_period: int,
) -> Tuple[Optional[float], Optional[float], List[Dict[str, Any]]]:
    """Returns (rvol, atr_percent, normalized D1 rows for candles_cache)."""
    try:
        data = await client.get_kline(
            category=category,
            symbol=symbol,
            interval="D",
            limit=max(lookback_days + 1, atr_period + 2),
        )
        raw_rows = list((data.get("result") or {}).get("list") or [])
        # ByBit returns newest-first; keep a copy for cache, reverse for OHLCV metrics.
        cache_rows = _kline_raw_to_cache_rows(raw_rows)
        chron = list(raw_rows)
        chron.reverse()
        highs, lows, closes, volumes = _parse_kline_rows(chron)
        rvol, atr = _volatility_from_ohlcv(highs, lows, closes, volumes, atr_period=atr_period)
        return rvol, atr, cache_rows
    except Exception:
        return None, None, []


def _persist_volatility_klines(
    db: Session,
    *,
    symbol: str,
    rows: List[Dict[str, Any]],
) -> int:
    if not rows:
        return 0
    from app.modules.robots.trading.data.providers.bybit_market import _upsert_bybit_candles

    try:
        return int(
            _upsert_bybit_candles(
                db,
                symbol=str(symbol).upper(),
                interval_label="D1",
                rows=rows,
            )
            or 0
        )
    except Exception as exc:
        logger.debug("volatility candles_cache upsert failed %s: %s", symbol, exc)
        return 0


def apply_derivative_filters(
    row: ScreeningRow,
    *,
    filters: CryptoUniverseFilters,
) -> bool:
    ok, reason = passes_funding_range(
        row.avg_funding_rate,
        min_rate=filters.min_funding_rate,
        max_rate=filters.max_funding_rate,
    )
    if not ok:
        row.filter_result = "rejected"
        row.reject_reason = reason
        return False
    ok, reason = passes_oi(filters.min_open_interest_usd, row.open_interest_usd)
    if not ok:
        row.filter_result = "rejected"
        row.reject_reason = reason
        return False
    ok, reason = passes_lsr(row.lsr, min_lsr=filters.min_lsr, max_lsr=filters.max_lsr)
    if not ok:
        row.filter_result = "rejected"
        row.reject_reason = reason
        return False
    return True


def apply_volatility_filters(
    row: ScreeningRow,
    *,
    filters: CryptoUniverseFilters,
) -> bool:
    ok, reason = passes_rvol(filters.min_rvol, row.rvol)
    if not ok:
        row.filter_result = "rejected"
        row.reject_reason = reason
        return False
    ok, reason = passes_atr_percent(
        row.atr_percent,
        min_pct=filters.min_atr_percent,
        max_pct=filters.max_atr_percent,
    )
    if not ok:
        row.filter_result = "rejected"
        row.reject_reason = reason
        return False
    return True


async def enrich_derivative_metrics_live(
    client: BybitHttpClient,
    rows: List[ScreeningRow],
    *,
    filters: CryptoUniverseFilters,
    db: Optional[Session] = None,
) -> Dict[str, int]:
    """Fill funding/OI/LSR. Prefer DB cache (TTL); API only on miss. Returns hit/miss counters.

    API-fetched rows are written to history tables and committed incrementally so a
    worker kill mid-screening still leaves reusable cache for the next run.
    """
    stats = {
        "symbols": len(rows),
        "funding_cache_hits": 0,
        "funding_api": 0,
        "oi_cache_hits": 0,
        "oi_api": 0,
        "lsr_cache_hits": 0,
        "lsr_api": 0,
        "cache_commits": 0,
    }
    if not rows:
        return stats

    symbols = [r.symbol for r in rows]
    funding_cache: Dict[str, float] = {}
    oi_cache: Dict[str, float] = {}
    lsr_cache: Dict[str, Tuple[float, float, float]] = {}
    if db is not None:
        try:
            funding_cache = _bulk_load_funding_avg_from_cache(
                db,
                symbols=symbols,
                category=filters.category,
                lookback_hours=filters.funding_lookback_hours,
            )
            oi_cache = _bulk_load_oi_from_cache(
                db,
                symbols=symbols,
                category=filters.category,
            )
            lsr_cache = _bulk_load_lsr_from_cache(
                db,
                symbols=symbols,
                category=filters.category,
            )
        except Exception as exc:
            logger.warning("derivative cache bulk load failed: %s", exc)
            funding_cache, oi_cache, lsr_cache = {}, {}, {}

    pending_commits = 0
    commit_every = max(1, int(DERIVATIVE_CACHE_COMMIT_EVERY))

    for row in rows:
        sym = row.symbol.upper()
        dirty = False
        fetched_oi = False
        fetched_lsr = False
        snapshot_time = datetime.now(timezone.utc)

        if sym in funding_cache:
            row.avg_funding_rate = funding_cache[sym]
            stats["funding_cache_hits"] += 1
        else:
            avg, raw = await _fetch_avg_funding_live(
                client,
                category=filters.category,
                symbol=row.symbol,
                lookback_hours=filters.funding_lookback_hours,
            )
            row.avg_funding_rate = avg
            stats["funding_api"] += 1
            if db is not None and raw:
                try:
                    _persist_funding_history_rows(
                        db,
                        symbol=row.symbol,
                        category=filters.category,
                        rows=raw,
                    )
                    dirty = True
                except Exception as exc:
                    logger.debug("funding cache upsert failed %s: %s", row.symbol, exc)

        if sym in oi_cache:
            row.open_interest_usd = oi_cache[sym]
            stats["oi_cache_hits"] += 1
        else:
            row.open_interest_usd = await _fetch_open_interest_usd_live(
                client,
                category=filters.category,
                symbol=row.symbol,
                last_price=row.lastPrice,
            )
            stats["oi_api"] += 1
            fetched_oi = row.open_interest_usd is not None

        if sym in lsr_cache:
            row.lsr, row.long_ratio, row.short_ratio = lsr_cache[sym]
            stats["lsr_cache_hits"] += 1
        else:
            row.lsr, row.long_ratio, row.short_ratio = await _fetch_lsr_live(
                client,
                category=filters.category,
                symbol=row.symbol,
            )
            stats["lsr_api"] += 1
            fetched_lsr = (
                row.lsr is not None
                and row.long_ratio is not None
                and row.short_ratio is not None
            )

        if db is not None and (fetched_oi or fetched_lsr):
            try:
                # Persist only freshly fetched legs; cache hits stay as-is in history.
                oi_val = row.open_interest_usd if fetched_oi else None
                lsr_val = row.lsr if fetched_lsr else None
                long_val = row.long_ratio if fetched_lsr else None
                short_val = row.short_ratio if fetched_lsr else None
                partial = ScreeningRow(
                    symbol=row.symbol,
                    turnover24h=row.turnover24h,
                    lastPrice=row.lastPrice,
                    spreadPercent=row.spreadPercent,
                    score=row.score,
                    open_interest_usd=oi_val,
                    lsr=lsr_val,
                    long_ratio=long_val,
                    short_ratio=short_val,
                )
                _upsert_oi_lsr_cache(
                    db,
                    row=partial,
                    instrument_category=filters.category,
                    snapshot_time=snapshot_time,
                )
                dirty = True
            except Exception as exc:
                logger.debug("oi/lsr cache upsert failed %s: %s", row.symbol, exc)

        if db is not None and dirty:
            pending_commits += 1
            if pending_commits >= commit_every:
                if _commit_derivative_cache(db):
                    stats["cache_commits"] += 1
                pending_commits = 0

    if db is not None and pending_commits > 0:
        if _commit_derivative_cache(db):
            stats["cache_commits"] += 1

    logger.info(
        "crypto derivative enrich: symbols=%s funding cache/api=%s/%s oi=%s/%s lsr=%s/%s commits=%s",
        stats["symbols"],
        stats["funding_cache_hits"],
        stats["funding_api"],
        stats["oi_cache_hits"],
        stats["oi_api"],
        stats["lsr_cache_hits"],
        stats["lsr_api"],
        stats["cache_commits"],
    )
    return stats


async def enrich_volatility_metrics_live(
    client: BybitHttpClient,
    rows: List[ScreeningRow],
    *,
    filters: CryptoUniverseFilters,
    db: Optional[Session] = None,
) -> Dict[str, int]:
    """Fill rvol/ATR%. Prefer bybit D1 candles_cache; API get_kline only on miss.

    API klines are upserted into candles_cache and committed incrementally.
    """
    stats = {
        "symbols": len(rows),
        "cache_hits": 0,
        "api": 0,
        "kline_rows_written": 0,
        "cache_commits": 0,
    }
    if not rows:
        return stats

    vol_cache: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    if db is not None:
        vol_cache = _bulk_load_volatility_from_candles_cache(
            db,
            symbols=[r.symbol for r in rows],
            lookback_days=filters.lookback_days,
            atr_period=filters.atr_period,
        )

    pending_commits = 0
    commit_every = max(1, int(DERIVATIVE_CACHE_COMMIT_EVERY))

    for row in rows:
        sym = row.symbol.upper()
        cached = vol_cache.get(sym)
        if cached is not None:
            rvol_c, atr_c = cached
            need_rvol = filters.min_rvol is not None
            need_atr = filters.min_atr_percent is not None or filters.max_atr_percent is not None
            ok = True
            if need_rvol and rvol_c is None:
                ok = False
            if need_atr and atr_c is None:
                ok = False
            if not need_rvol and not need_atr and rvol_c is None and atr_c is None:
                ok = False
            if ok:
                row.rvol, row.atr_percent = rvol_c, atr_c
                stats["cache_hits"] += 1
                continue

        rvol, atr, cache_rows = await _fetch_volatility_metrics_live(
            client,
            category=filters.category,
            symbol=row.symbol,
            lookback_days=filters.lookback_days,
            atr_period=filters.atr_period,
        )
        row.rvol, row.atr_percent = rvol, atr
        stats["api"] += 1

        if db is not None and cache_rows:
            wrote = _persist_volatility_klines(db, symbol=row.symbol, rows=cache_rows)
            stats["kline_rows_written"] += wrote
            if wrote > 0:
                pending_commits += 1
                if pending_commits >= commit_every:
                    if _commit_derivative_cache(db):
                        stats["cache_commits"] += 1
                    pending_commits = 0

    if db is not None and pending_commits > 0:
        if _commit_derivative_cache(db):
            stats["cache_commits"] += 1

    logger.info(
        "crypto volatility enrich: symbols=%s cache/api=%s/%s kline_rows=%s commits=%s",
        stats["symbols"],
        stats["cache_hits"],
        stats["api"],
        stats["kline_rows_written"],
        stats["cache_commits"],
    )
    return stats


async def screen_bybit_universe_live(
    tickers: Iterable[Dict[str, Any]],
    *,
    client: BybitHttpClient,
    filters: CryptoUniverseFilters,
    db: Optional[Session] = None,
) -> Tuple[List[ScreeningRow], List[ScreeningRow]]:
    """Multi-stage live screening: basic → derivatives → volatility."""
    basic_ok, basic_rejected = apply_basic_filters(tickers, filters=filters)
    all_rejected = list(basic_rejected)

    derivative_candidates = basic_ok
    if _derivative_filters_enabled(filters) and derivative_candidates:
        await enrich_derivative_metrics_live(
            client, derivative_candidates, filters=filters, db=db
        )
        passed: List[ScreeningRow] = []
        for row in derivative_candidates:
            if apply_derivative_filters(row, filters=filters):
                passed.append(row)
            else:
                all_rejected.append(row)
        derivative_candidates = passed

    final_candidates = derivative_candidates
    if _volatility_filters_enabled(filters) and final_candidates:
        await enrich_volatility_metrics_live(
            client, final_candidates, filters=filters, db=db
        )
        passed = []
        for row in final_candidates:
            if apply_volatility_filters(row, filters=filters):
                passed.append(row)
            else:
                all_rejected.append(row)
        final_candidates = passed

    final_candidates.sort(key=lambda x: x.score, reverse=True)
    capped = final_candidates[: max(1, int(filters.limit))]
    return capped, all_rejected


# Process-local cache for full-universe GET /v5/market/tickers (no symbol filter).
_TICKERS_CACHE: Dict[Tuple[str, bool], Tuple[float, List[Dict[str, Any]]]] = {}
_tickers_fetch_lock = asyncio.Lock()
TICKERS_CACHE_TTL_SECONDS = 120


def clear_bybit_tickers_cache() -> None:
    _TICKERS_CACHE.clear()


async def fetch_bybit_tickers(
    *,
    api_key: str,
    api_secret: str,
    testnet: bool,
    category: str,
    ttl_seconds: Optional[int] = None,
    force: bool = False,
    user_id: Optional[int] = None,
    token_id: Optional[int] = None,
    context_type: Optional[str] = "bybit_http",
    context_ref: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Full-category tickers list with short TTL cache.

    Single-symbol quotes still go through BybitHttpClient.get_tickers(symbol=...).
    """
    cat = str(category or "linear").strip().lower() or "linear"
    key = (cat, bool(testnet))
    ttl = TICKERS_CACHE_TTL_SECONDS if ttl_seconds is None else max(0, int(ttl_seconds))
    now = time.time()

    if not force and ttl > 0:
        cached = _TICKERS_CACHE.get(key)
        if cached is not None and cached[0] > now:
            logger.info(
                "bybit tickers cache hit: category=%s testnet=%s rows=%s ttl_left=%.0fs",
                cat,
                testnet,
                len(cached[1]),
                cached[0] - now,
            )
            return copy.deepcopy(cached[1])

    async with _tickers_fetch_lock:
        # Re-check after lock (another coroutine may have filled cache).
        now = time.time()
        if not force and ttl > 0:
            cached = _TICKERS_CACHE.get(key)
            if cached is not None and cached[0] > now:
                return copy.deepcopy(cached[1])

        client = BybitHttpClient(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
            user_id=user_id,
            token_id=token_id,
            context_type=context_type,
            context_ref=context_ref,
        )
        try:
            payload = await client.get_tickers(category=cat)
            rows = list((payload.get("result") or {}).get("list") or [])
        finally:
            await client.close()

        if ttl > 0:
            _TICKERS_CACHE[key] = (now + ttl, copy.deepcopy(rows))
            logger.info(
                "bybit tickers cache store: category=%s testnet=%s rows=%s ttl=%ss",
                cat,
                testnet,
                len(rows),
                ttl,
            )
        return rows


def _find_active_bybit_token(db: Session, user_id: int, token_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if token_id is not None:
        row = db.execute(
            text(
                f"""
                SELECT token, extra_data
                FROM api_tokens
                WHERE id = :tid
                  AND user_id = :uid
                  AND status = 1
                  AND (LOWER(CAST(token_type AS text)) = '2' OR LOWER(CAST(token_type AS text)) = 'bybit')
                LIMIT 1
                """
            ),
            {"tid": int(token_id), "uid": int(user_id)},
        ).first()
    else:
        row = db.execute(
            text(
                f"""
                SELECT token, extra_data
                FROM api_tokens
                WHERE user_id = :uid
                  AND status = 1
                  AND (LOWER(CAST(token_type AS text)) = '2' OR LOWER(CAST(token_type AS text)) = 'bybit')
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"uid": int(user_id)},
        ).first()
    if not row:
        return None
    extra = row[1] if isinstance(row[1], dict) else {}
    return {
        "token": str(row[0] or ""),
        "token_secret": str(extra.get("token_secret") or ""),
        "testnet": False,
    }


def _resolve_filters(config: Dict[str, Any]) -> CryptoUniverseFilters:
    cu = config.get("crypto_universe") if isinstance(config.get("crypto_universe"), dict) else {}
    bybit = config.get("bybit") if isinstance(config.get("bybit"), dict) else {}
    min_turnover = cu.get("min_volume_24h_usd")
    if min_turnover is None:
        min_turnover = cu.get("min_turnover_24h_usd")
    if min_turnover is None:
        min_turnover = 50_000_000.0
    if cu.get("max_spread_bps") is not None:
        max_spread_pct = float(cu.get("max_spread_bps")) / 100.0
    else:
        max_spread_pct = float(cu.get("max_spread_pct") or 0.15)

    def _opt_float(key: str) -> Optional[float]:
        if key not in cu or cu.get(key) is None:
            return None
        try:
            return float(cu[key])
        except (TypeError, ValueError):
            return None

    return CryptoUniverseFilters(
        min_turnover_24h_usd=float(min_turnover),
        max_spread_pct=max_spread_pct,
        min_last_price=float(cu["min_last_price"]) if cu.get("min_last_price") is not None else 0.05,
        limit=int(cu.get("limit") or 80),
        category=str(cu.get("category") or bybit.get("instrument_category") or "linear"),
        quote_coin=str(cu.get("quote_coin") or "USDT"),
        min_funding_rate=_opt_float("min_funding_rate") if "min_funding_rate" in cu else -0.0001,
        max_funding_rate=_opt_float("max_funding_rate") if "max_funding_rate" in cu else 0.0002,
        funding_lookback_hours=int(cu.get("funding_lookback_hours") or 8),
        min_open_interest_usd=_opt_float("min_open_interest_usd") if "min_open_interest_usd" in cu else 20_000_000.0,
        min_lsr=_opt_float("min_lsr") if "min_lsr" in cu else 0.5,
        max_lsr=_opt_float("max_lsr") if "max_lsr" in cu else 1.5,
        min_rvol=_opt_float("min_rvol") if "min_rvol" in cu else 2.0,
        min_atr_percent=_opt_float("min_atr_percent") if "min_atr_percent" in cu else 1.5,
        max_atr_percent=_opt_float("max_atr_percent") if "max_atr_percent" in cu else 10.0,
        lookback_days=int(cu.get("lookback_days") or 20),
        atr_period=int(cu.get("atr_period") or 14),
    )


def resolve_crypto_universe_filters(config: Dict[str, Any]) -> CryptoUniverseFilters:
    """Public resolver: Type2BybitConfig fields → runtime filters."""
    return _resolve_filters(config)


def _upsert_oi_lsr_cache(
    db: Session,
    *,
    row: ScreeningRow,
    instrument_category: str,
    snapshot_time: datetime,
) -> None:
    if row.open_interest_usd is not None:
        db.execute(
            text(
                f"""
                INSERT INTO bybit_open_interest_history
                (symbol, snapshot_time, open_interest_usd, instrument_category, created_at)
                VALUES (:symbol, :snapshot_time, :oi_usd, :category, NOW())
                ON CONFLICT (symbol, snapshot_time, instrument_category) DO NOTHING
                """
            ),
            {
                "symbol": row.symbol,
                "snapshot_time": snapshot_time,
                "oi_usd": row.open_interest_usd,
                "category": instrument_category,
            },
        )
    if row.lsr is not None and row.long_ratio is not None and row.short_ratio is not None:
        db.execute(
            text(
                f"""
                INSERT INTO bybit_lsr_history
                (symbol, snapshot_time, long_ratio, short_ratio, instrument_category, created_at)
                VALUES (:symbol, :snapshot_time, :long_ratio, :short_ratio, :category, NOW())
                ON CONFLICT (symbol, snapshot_time, instrument_category) DO NOTHING
                """
            ),
            {
                "symbol": row.symbol,
                "snapshot_time": snapshot_time,
                "long_ratio": row.long_ratio,
                "short_ratio": row.short_ratio,
                "category": instrument_category,
            },
        )


def _persist_screening_rows(
    db: Session,
    *,
    robot_id: int,
    trade_date: date,
    rows: List[ScreeningRow],
    filters: CryptoUniverseFilters,
) -> None:
    for row in rows:
        db.execute(
            text(
                f"""
                INSERT INTO crypto_universe_daily (
                    robot_id,
                    trade_date,
                    symbol,
                    source,
                    filter_result,
                    reject_reason,
                    turnover_24h,
                    last_price,
                    spread_percent,
                    meta_payload
                ) VALUES (
                    :rid,
                    :trade_date,
                    :symbol,
                    :source,
                    :filter_result,
                    :reject_reason,
                    :turnover_24h,
                    :last_price,
                    :spread_percent,
                    CAST(:meta_payload AS jsonb)
                )
                ON CONFLICT (robot_id, trade_date, symbol)
                DO UPDATE SET
                    source = EXCLUDED.source,
                    filter_result = EXCLUDED.filter_result,
                    reject_reason = EXCLUDED.reject_reason,
                    turnover_24h = EXCLUDED.turnover_24h,
                    last_price = EXCLUDED.last_price,
                    spread_percent = EXCLUDED.spread_percent,
                    meta_payload = EXCLUDED.meta_payload,
                    created_at = NOW()
                """
            ),
            {
                "rid": int(robot_id),
                "trade_date": trade_date,
                "symbol": row.symbol,
                "source": "crypto_screening",
                "filter_result": row.filter_result,
                "reject_reason": row.reject_reason,
                "turnover_24h": row.turnover24h,
                "last_price": row.lastPrice,
                "spread_percent": row.spreadPercent,
                "meta_payload": json.dumps(
                    {
                        "score": row.score,
                        "category": filters.category,
                        "quote_coin": filters.quote_coin,
                        "avg_funding_rate": row.avg_funding_rate,
                        "open_interest_usd": row.open_interest_usd,
                        "lsr": row.lsr,
                        "rvol": row.rvol,
                        "atr_percent": row.atr_percent,
                        **row.meta,
                    },
                    ensure_ascii=False,
                ),
            },
        )


def _screening_refresh_minutes(config: Dict[str, Any]) -> int:
    cu = config.get("crypto_universe") if isinstance(config.get("crypto_universe"), dict) else {}
    refresh = cu.get("refresh") if isinstance(cu.get("refresh"), dict) else {}
    try:
        return max(0, int(refresh.get("every_minutes") or 0))
    except (TypeError, ValueError):
        return 0


def _parse_iso_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text_v = str(value).strip()
    if not text_v:
        return None
    try:
        dt = datetime.fromisoformat(text_v.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _load_accepted_symbols_today(db: Session, *, robot_id: int) -> List[str]:
    trade_date = datetime.now(timezone.utc).date()
    rows = db.execute(
        text(
            f"""
            SELECT symbol
            FROM crypto_universe_daily
            WHERE robot_id = :rid
              AND trade_date = :trade_date
              AND LOWER(COALESCE(filter_result, '')) = 'accepted'
            ORDER BY symbol
            """
        ),
        {"rid": int(robot_id), "trade_date": trade_date},
    ).fetchall()
    return [str(r[0]).upper() for r in rows if r and r[0]]


def _latest_screening_at(db: Session, *, robot_id: int, config: Dict[str, Any]) -> Optional[datetime]:
    """Best-effort freshness: config.last_screened_at or MAX(created_at) for today."""
    cu = config.get("crypto_universe") if isinstance(config.get("crypto_universe"), dict) else {}
    from_cfg = _parse_iso_dt(cu.get("last_screened_at"))
    trade_date = datetime.now(timezone.utc).date()
    row = db.execute(
        text(
            f"""
            SELECT MAX(created_at)
            FROM crypto_universe_daily
            WHERE robot_id = :rid AND trade_date = :trade_date
            """
        ),
        {"rid": int(robot_id), "trade_date": trade_date},
    ).first()
    from_db: Optional[datetime] = None
    if row and row[0] is not None:
        ts = row[0]
        from_db = ts if getattr(ts, "tzinfo", None) else ts.replace(tzinfo=timezone.utc)
    candidates = [t for t in (from_cfg, from_db) if t is not None]
    return max(candidates) if candidates else None


def try_reuse_fresh_crypto_universe(
    db: Session,
    *,
    robot_id: int,
    config: Dict[str, Any],
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """
    If last screening is within refresh.every_minutes, reuse accepted symbols
    without ByBit tickers/enrich HTTP.
    """
    ttl_min = _screening_refresh_minutes(config)
    if ttl_min <= 0:
        return None
    now_utc = now or datetime.now(timezone.utc)
    screened_at = _latest_screening_at(db, robot_id=robot_id, config=config)
    if screened_at is None:
        return None
    age_sec = (now_utc - screened_at).total_seconds()
    if age_sec < 0 or age_sec >= ttl_min * 60:
        return None

    symbols = _load_accepted_symbols_today(db, robot_id=robot_id)
    if not symbols:
        cu = config.get("crypto_universe") if isinstance(config.get("crypto_universe"), dict) else {}
        symbols = [
            str(s).strip().upper()
            for s in (config.get("allowed_symbols") or cu.get("allowed_symbols") or [])
            if str(s).strip()
        ]
    if not symbols:
        return None

    cu = config.get("crypto_universe") if isinstance(config.get("crypto_universe"), dict) else {}
    stats = cu.get("stats") if isinstance(cu.get("stats"), dict) else {}
    logger.info(
        "crypto universe reuse: robot_id=%s symbols=%s age_sec=%.0f ttl_min=%s",
        robot_id,
        len(symbols),
        age_sec,
        ttl_min,
    )
    return {
        "symbols": symbols,
        "accepted": len(symbols),
        "scanned": int(stats.get("scanned") or len(symbols)),
        "rejected": int(stats.get("rejected") or 0),
        "message": (
            f"reused fresh screening (age {int(age_sec)}s < {ttl_min}m); "
            "no ByBit tickers/enrich"
        ),
        "skipped": False,
        "reused": True,
    }


async def rebuild_crypto_universe(
    db: Session,
    *,
    robot_id: int,
    user_id: int,
    config: Dict[str, Any],
    force: bool = False,
) -> Dict[str, Any]:
    if not force:
        reused = try_reuse_fresh_crypto_universe(db, robot_id=robot_id, config=config)
        if reused is not None:
            # Keep robot config.allowed_symbols aligned without rewriting last_screened_at.
            if list(config.get("allowed_symbols") or []) != reused["symbols"]:
                config["allowed_symbols"] = list(reused["symbols"])
                db.execute(
                    text(
                        f"""
                        UPDATE robots
                        SET config = CAST(:config AS jsonb),
                            date_modification = :now,
                            usermod = :uid
                        WHERE id = :rid AND user_id = :uid
                        """
                    ),
                    {
                        "rid": int(robot_id),
                        "uid": int(user_id),
                        "config": json.dumps(config, ensure_ascii=False),
                        "now": datetime.now(timezone.utc),
                    },
                )
                db.commit()
            return reused

    token_row = _find_active_bybit_token(db, user_id)
    if not token_row:
        return {
            "symbols": list(config.get("allowed_symbols") or []),
            "accepted": 0,
            "scanned": 0,
            "message": "Активный ByBit токен не найден",
            "skipped": True,
            "reused": False,
        }
    api_key = token_row["token"]
    api_secret = token_row["token_secret"]
    if not api_key or not api_secret:
        return {
            "symbols": list(config.get("allowed_symbols") or []),
            "accepted": 0,
            "scanned": 0,
            "message": "ByBit token/token_secret не заполнены",
            "skipped": True,
            "reused": False,
        }

    filters = _resolve_filters(config)
    tickers = await fetch_bybit_tickers(
        api_key=api_key,
        api_secret=api_secret,
        testnet=False,
        category=filters.category,
        force=force,
    )

    client = BybitHttpClient(
        testnet=False,
        api_key=api_key,
        api_secret=api_secret,
    )
    try:
        accepted_rows, rejected_rows = await screen_bybit_universe_live(
            tickers,
            client=client,
            filters=filters,
            db=db,
        )
    finally:
        await client.close()

    symbols = [r.symbol for r in accepted_rows]
    trade_date = datetime.now(timezone.utc).date()
    snapshot_time = datetime.now(timezone.utc)

    db.execute(
        text(
            f"""
            DELETE FROM crypto_universe_daily
            WHERE robot_id = :rid AND trade_date = :trade_date
            """
        ),
        {"rid": int(robot_id), "trade_date": trade_date},
    )

    for row in accepted_rows + rejected_rows:
        _upsert_oi_lsr_cache(
            db,
            row=row,
            instrument_category=filters.category,
            snapshot_time=snapshot_time,
        )
    _persist_screening_rows(
        db,
        robot_id=robot_id,
        trade_date=trade_date,
        rows=accepted_rows + rejected_rows,
        filters=filters,
    )

    config["allowed_symbols"] = symbols
    config["crypto_universe"] = {
        **(config.get("crypto_universe") if isinstance(config.get("crypto_universe"), dict) else {}),
        "last_screened_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "scanned": len(tickers),
            "accepted": len(symbols),
            "rejected": len(rejected_rows),
            "category": filters.category,
            "quote_coin": filters.quote_coin,
        },
    }
    db.execute(
        text(
            f"""
            UPDATE robots
            SET config = CAST(:config AS jsonb),
                date_modification = :now,
                usermod = :uid
            WHERE id = :rid AND user_id = :uid
            """
        ),
        {
            "rid": int(robot_id),
            "uid": int(user_id),
            "config": json.dumps(config, ensure_ascii=False),
            "now": datetime.now(timezone.utc),
        },
    )
    db.commit()
    return {
        "symbols": symbols,
        "accepted": len(symbols),
        "scanned": len(tickers),
        "rejected": len(rejected_rows),
        "message": None,
        "skipped": False,
        "reused": False,
    }


def load_historical_funding_avg(
    db: Session,
    *,
    symbol: str,
    as_of: datetime,
    instrument_category: str,
    lookback_hours: int,
) -> Optional[float]:
    from app.core.db_retry import run_db_read_with_retry

    from_dt = as_of - timedelta(hours=max(1, int(lookback_hours)))

    def _query() -> Optional[float]:
        rows = db.execute(
            text(
                f"""
            SELECT funding_rate
            FROM bybit_funding_history
            WHERE symbol = :symbol
              AND instrument_category = :category
              AND funding_time >= :from_dt
              AND funding_time < :as_of
            ORDER BY funding_time
            """
            ),
            {
                "symbol": symbol.upper(),
                "category": instrument_category,
                "from_dt": from_dt,
                "as_of": as_of,
            },
        ).fetchall()
        return avg_funding_rate([{"funding_rate": r[0]} for r in rows])

    return run_db_read_with_retry(db, _query)


def load_historical_oi_usd(
    db: Session,
    *,
    symbol: str,
    as_of: datetime,
    instrument_category: str,
) -> Optional[float]:
    from app.core.db_retry import run_db_read_with_retry

    def _query() -> Optional[float]:
        row = db.execute(
            text(
                f"""
            SELECT open_interest_usd
            FROM bybit_open_interest_history
            WHERE symbol = :symbol
              AND instrument_category = :category
              AND snapshot_time < :as_of
            ORDER BY snapshot_time DESC
            LIMIT 1
            """
            ),
            {"symbol": symbol.upper(), "category": instrument_category, "as_of": as_of},
        ).first()
        if not row:
            return None
        return _safe_float(row[0])

    return run_db_read_with_retry(db, _query)


def load_historical_lsr(
    db: Session,
    *,
    symbol: str,
    as_of: datetime,
    instrument_category: str,
) -> Optional[float]:
    from app.core.db_retry import run_db_read_with_retry

    def _query() -> Optional[float]:
        row = db.execute(
            text(
                f"""
            SELECT long_ratio, short_ratio
            FROM bybit_lsr_history
            WHERE symbol = :symbol
              AND instrument_category = :category
              AND snapshot_time < :as_of
            ORDER BY snapshot_time DESC
            LIMIT 1
            """
            ),
            {"symbol": symbol.upper(), "category": instrument_category, "as_of": as_of},
        ).first()
        if not row:
            return None
        buy = _safe_float(row[0])
        sell = _safe_float(row[1])
        if buy is None or sell is None:
            return None
        return compute_lsr(buy, sell)

    return run_db_read_with_retry(db, _query)
