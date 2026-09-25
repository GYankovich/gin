"""Live ingest: candles → candles_cache, ticks, depth_latest, heartbeat."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.osengine.intervals_map import normalize_cache_interval
from app.modules.osengine.schemas import (
    IngestCandleItem,
    IngestDepthItem,
    IngestTickItem,
)
from app.modules.osengine.stats import LiveIngestStatus
from app.modules.osengine.types import InstrumentKey

logger = logging.getLogger(__name__)


def _market() -> str:
    return (settings.OSENGINE_MARKET_KEY or "osengine").strip() or "osengine"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _touch_heartbeat(
    db: Session,
    *,
    stream: str,
    last_at: Optional[datetime],
    rows_delta: int,
    subscribed_instruments: Optional[int] = None,
    detail: Optional[str] = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO osengine_ingest_heartbeat
                (stream, last_at, subscribed_instruments, rows_total, detail, updated_at)
            VALUES
                (:stream, :last_at, :sub, :rows, :detail, CURRENT_TIMESTAMP)
            ON CONFLICT (stream) DO UPDATE SET
                last_at = COALESCE(EXCLUDED.last_at, osengine_ingest_heartbeat.last_at),
                subscribed_instruments = CASE
                    WHEN :sub_set THEN EXCLUDED.subscribed_instruments
                    ELSE osengine_ingest_heartbeat.subscribed_instruments
                END,
                rows_total = osengine_ingest_heartbeat.rows_total + EXCLUDED.rows_total,
                detail = COALESCE(EXCLUDED.detail, osengine_ingest_heartbeat.detail),
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "stream": stream,
            "last_at": last_at,
            "sub": int(subscribed_instruments) if subscribed_instruments is not None else 0,
            "sub_set": subscribed_instruments is not None,
            "rows": int(rows_delta),
            "detail": detail,
        },
    )


def ingest_candles(
    db: Session,
    items: Sequence[IngestCandleItem],
    *,
    subscribed_instruments: Optional[int] = None,
) -> int:
    if not items:
        return 0
    market = _market()
    accepted = 0
    last_at: Optional[datetime] = None
    for item in items:
        key = InstrumentKey(ticker=item.ticker, board=item.board).normalized()
        ts = _ensure_aware(item.time)
        interval = normalize_cache_interval(item.interval)
        db.execute(
            text(
                """
                INSERT INTO candles_cache
                (market, instrument_id, ticker, interval, candle_time, open, high, low, close, volume, source, updated_at)
                VALUES
                (:market, :iid, :ticker, :interval, :ts, :o, :h, :l, :c, :v, 'osengine_live', NOW())
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
                "iid": key.cache_id,
                "ticker": key.ticker,
                "interval": interval,
                "ts": ts,
                "o": item.open,
                "h": item.high,
                "l": item.low,
                "c": item.close,
                "v": int(item.volume) if float(item.volume).is_integer() else item.volume,
            },
        )
        accepted += 1
        if last_at is None or ts > last_at:
            last_at = ts
    _touch_heartbeat(
        db,
        stream="candles",
        last_at=last_at,
        rows_delta=accepted,
        subscribed_instruments=subscribed_instruments,
    )
    return accepted


def ingest_ticks(
    db: Session,
    items: Sequence[IngestTickItem],
    *,
    subscribed_instruments: Optional[int] = None,
) -> int:
    if not items:
        return 0
    market = _market()
    accepted = 0
    last_at: Optional[datetime] = None
    for item in items:
        key = InstrumentKey(ticker=item.ticker, board=item.board).normalized()
        ts = _ensure_aware(item.time)
        trade_id = (item.trade_id or "").strip()
        try:
            result = db.execute(
                text(
                    """
                    INSERT INTO market_ticks
                    (market, instrument_id, ticker, exchange_time, price, quantity, side, trade_id, ingested_at)
                    VALUES
                    (:market, :iid, :ticker, :ts, :price, :qty, :side, :trade_id, NOW())
                    ON CONFLICT (market, instrument_id, exchange_time, trade_id, price, quantity)
                    DO NOTHING
                    """
                ),
                {
                    "market": market,
                    "iid": key.cache_id,
                    "ticker": key.ticker,
                    "ts": ts,
                    "price": item.price,
                    "qty": item.quantity,
                    "side": item.side,
                    "trade_id": trade_id,
                },
            )
            if result.rowcount:
                accepted += 1
        except Exception:
            logger.exception("osengine tick ingest failed ticker=%s", key.ticker)
            continue
        if last_at is None or ts > last_at:
            last_at = ts
    _touch_heartbeat(
        db,
        stream="ticks",
        last_at=last_at,
        rows_delta=accepted,
        subscribed_instruments=subscribed_instruments,
    )
    return accepted


def ingest_depth(
    db: Session,
    items: Sequence[IngestDepthItem],
    *,
    subscribed_instruments: Optional[int] = None,
) -> int:
    if not items:
        return 0
    market = _market()
    accepted = 0
    last_at: Optional[datetime] = None
    for item in items:
        key = InstrumentKey(ticker=item.ticker, board=item.board).normalized()
        ts = _ensure_aware(item.time) if item.time else _now()
        bids = [[lvl.price, lvl.quantity] for lvl in item.bids]
        asks = [[lvl.price, lvl.quantity] for lvl in item.asks]
        db.execute(
            text(
                """
                INSERT INTO market_depth_latest
                (market, instrument_id, ticker, bids, asks, exchange_time, updated_at)
                VALUES
                (:market, :iid, :ticker, CAST(:bids AS jsonb), CAST(:asks AS jsonb), :ts, NOW())
                ON CONFLICT (market, instrument_id) DO UPDATE SET
                    ticker = EXCLUDED.ticker,
                    bids = EXCLUDED.bids,
                    asks = EXCLUDED.asks,
                    exchange_time = EXCLUDED.exchange_time,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "market": market,
                "iid": key.cache_id,
                "ticker": key.ticker,
                "bids": json.dumps(bids),
                "asks": json.dumps(asks),
                "ts": ts,
            },
        )
        accepted += 1
        if last_at is None or ts > last_at:
            last_at = ts
    _touch_heartbeat(
        db,
        stream="depth",
        last_at=last_at,
        rows_delta=accepted,
        subscribed_instruments=subscribed_instruments,
    )
    return accepted


def read_live_status(db: Session) -> LiveIngestStatus:
    try:
        rows = db.execute(
            text(
                """
                SELECT stream, last_at, subscribed_instruments, detail, updated_at
                  FROM osengine_ingest_heartbeat
                """
            )
        ).mappings().all()
    except Exception:
        return LiveIngestStatus(
            enabled=bool(settings.OSENGINE_ENABLED),
            bridge_connected=False,
            detail="heartbeat table unavailable (run migration 0064)",
        )
    by_stream: Dict[str, Any] = {str(r["stream"]): dict(r) for r in rows}
    now = _now()
    last_times: List[datetime] = []
    for key in ("candles", "ticks", "depth"):
        row = by_stream.get(key) or {}
        ts = row.get("last_at") or row.get("updated_at")
        if ts is not None:
            if getattr(ts, "tzinfo", None) is None:
                ts = ts.replace(tzinfo=timezone.utc)
            last_times.append(ts)

    lag = None
    if last_times:
        newest = max(last_times)
        lag = max(0.0, (now - newest).total_seconds())

    sub = 0
    for row in by_stream.values():
        sub = max(sub, int(row.get("subscribed_instruments") or 0))

    def _iso(stream: str) -> Optional[str]:
        row = by_stream.get(stream) or {}
        ts = row.get("last_at")
        return ts.isoformat() if ts is not None else None

    connected = bool(last_times) and (lag is None or lag < 120.0)
    return LiveIngestStatus(
        enabled=bool(settings.OSENGINE_ENABLED) or bool(settings.OSENGINE_DATA_ROOT) or bool(by_stream),
        bridge_connected=connected,
        subscribed_instruments=sub,
        last_candle_at=_iso("candles"),
        last_tick_at=_iso("ticks"),
        last_depth_at=_iso("depth"),
        lag_seconds=lag,
        detail="ok" if connected else ("stale" if last_times else "no heartbeat yet"),
    )


__all__ = [
    "ingest_candles",
    "ingest_depth",
    "ingest_ticks",
    "read_live_status",
]
