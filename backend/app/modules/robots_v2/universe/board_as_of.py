"""Point-in-time board membership from OsEngine (no MOEX ISS).

TEMP: replaces ISS history listing for screener as-of / backtest universe.
Sources (in order): candles_cache D1 → snapshot history → OsEngine Data/ Day
folders → tqbr_securities intersected with cache → optional OsEngine snapshot ensure.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)


def _osengine_market() -> str:
    return (settings.OSENGINE_MARKET_KEY or "osengine").strip() or "osengine"


def _msk_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    tz_name = (getattr(settings, "OSENGINE_CANDLE_TZ", None) or "Europe/Moscow").strip()
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    day_start_local = datetime.combine(day, time.min, tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)
    return day_start_local.astimezone(timezone.utc), day_end_local.astimezone(timezone.utc)


def fetch_osengine_board_secids_from_cache(
    db: Session,
    day: date,
    *,
    market: Optional[str] = None,
) -> list[str]:
    """Tickers with a D1 bar on ``day`` in candles_cache (OsEngine market)."""
    market_key = (market or _osengine_market()).strip().lower() or "osengine"
    from_utc, to_utc = _msk_day_bounds_utc(day)
    rows = db.execute(
        text(
            """
            SELECT DISTINCT UPPER(instrument_id) AS ticker
            FROM candles_cache
            WHERE LOWER(market) = :market
              AND interval = 'D1'
              AND candle_time >= :from_dt
              AND candle_time < :to_dt
            ORDER BY ticker
            """
        ),
        {"market": market_key, "from_dt": from_utc, "to_dt": to_utc},
    ).fetchall()
    return [str(r[0]).strip().upper() for r in rows if r and r[0]]


def fetch_osengine_board_secids_from_snapshot(
    db: Session,
    board: str,
    day: date,
) -> list[str]:
    """Tickers from a SUCCESS market_snapshot_*_history row for ``day``."""
    board_u = (board or "TQBR").strip().upper() or "TQBR"
    day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    rows = db.execute(
        text(
            """
            SELECT DISTINCT UPPER(d.ticker) AS ticker
            FROM market_snapshot_history h
            JOIN market_snapshot_data_history d ON d.snapshot_id = h.id
            WHERE h.board = :board
              AND h.status = 'SUCCESS'
              AND h.snapshot_time >= :day_start
              AND h.snapshot_time < :day_end
            ORDER BY ticker
            """
        ),
        {"board": board_u, "day_start": day_start, "day_end": day_end},
    ).fetchall()
    return [str(r[0]).strip().upper() for r in rows if r and r[0]]


def list_osengine_day_tickers_from_data(*, limit: int = 500) -> list[str]:
    """SEC names that have a Day/ folder under OsEngine Data/."""
    from app.modules.osengine.file_index import resolve_data_root

    root = resolve_data_root()
    if root is None or not root.is_dir():
        return []
    tickers: set[str] = set()
    try:
        for set_dir in sorted(root.iterdir()):
            if not set_dir.is_dir():
                continue
            name_l = set_dir.name.lower()
            if name_l in ("temp",):
                continue
            for sec_dir in set_dir.iterdir():
                if not sec_dir.is_dir():
                    continue
                day_dir = sec_dir / "Day"
                if not day_dir.is_dir():
                    continue
                raw = sec_dir.name.upper().strip()
                ticker = raw.split("_", 1)[0] if raw else ""
                if ticker:
                    tickers.add(ticker)
                if len(tickers) >= limit:
                    return sorted(tickers)[:limit]
    except OSError as exc:
        logger.warning("osengine Data/ board scan failed: %s", exc)
    return sorted(tickers)[:limit]


def list_board_tickers_from_tqbr(db: Session, board: str, *, limit: int = 400) -> list[str]:
    """Active names from tqbr_securities (local reference, not ISS)."""
    from app.modules.robots.moex_securities_updater import queries as moex_q

    sql, params = moex_q.build_equity_universe_query(board=board, active_only=True)
    rows = db.execute(text(sql), params).fetchall()
    tickers = sorted({str(r[0]).strip().upper() for r in rows if r and r[0]})
    return tickers[:limit]


def fetch_moex_board_secids_on_day(
    board: str,
    day: date,
    db: Session | None = None,
) -> list[str]:
    """Board SECID list for ``day`` from OsEngine cache / snapshot (ISS removed)."""
    own_session = False
    if db is None:
        from app.core.database import SessionLocal

        db = SessionLocal()
        own_session = True
    try:
        tickers = fetch_osengine_board_secids_from_cache(db, day)
        if tickers:
            return tickers
        tickers = fetch_osengine_board_secids_from_snapshot(db, board, day)
        if tickers:
            return tickers
        return []
    finally:
        if own_session:
            db.close()


async def list_moex_board_tickers_as_of(
    board: str,
    as_of: date,
    *,
    db: Session | None = None,
    lookback_days: int = 12,
) -> list[str]:
    """Nearest session on or before ``as_of`` using OsEngine-backed sources."""
    own_session = False
    if db is None:
        from app.core.database import SessionLocal

        db = SessionLocal()
        own_session = True
    try:
        for i in range(max(1, lookback_days)):
            day = as_of - timedelta(days=i)
            tickers = fetch_osengine_board_secids_from_cache(db, day)
            if tickers:
                return tickers
            tickers = fetch_osengine_board_secids_from_snapshot(db, board, day)
            if tickers:
                return tickers

        # Prefer tickers that already have Day files under Data/
        data_tickers = list_osengine_day_tickers_from_data()
        if data_tickers:
            return data_tickers

        # Local TQBR reference table (no network)
        ref = list_board_tickers_from_tqbr(db, board)
        if ref:
            return ref

        # Last resort: ensure one OsEngine day snapshot for as_of, then re-read
        try:
            from app.modules.osengine.snapshots import ensure_daily_snapshot_from_osengine

            await ensure_daily_snapshot_from_osengine(db, day=as_of, board=board)
            tickers = fetch_osengine_board_secids_from_cache(db, as_of)
            if tickers:
                return tickers
            tickers = fetch_osengine_board_secids_from_snapshot(db, board, as_of)
            if tickers:
                return tickers
        except Exception:
            logger.exception(
                "osengine board_as_of ensure snapshot failed board=%s as_of=%s",
                board,
                as_of.isoformat(),
            )

        return list_moex_symbols_from_cache(db, as_of=as_of, market=_osengine_market())
    finally:
        if own_session:
            db.close()


def list_moex_symbols_from_cache(
    db: Session,
    *,
    as_of: date,
    market: str | None = None,
) -> list[str]:
    """Tickers that already have candles strictly before as_of (causal fallback)."""
    market_key = (market or _osengine_market()).strip().lower() or "osengine"
    end = datetime.combine(as_of, time.min, tzinfo=timezone.utc)
    rows = db.execute(
        text(
            """
            SELECT DISTINCT instrument_id
            FROM candles_cache
            WHERE LOWER(market) = :market
              AND candle_time < :end
            ORDER BY instrument_id
            """
        ),
        {"market": market_key, "end": end},
    ).fetchall()
    return [str(r[0]).strip().upper() for r in rows if r and r[0]]


# Cap MCP/file ensure during screener so we do not request full TQBR in one shot.
_SCREENER_ENSURE_LIMIT = 400


def narrow_screener_candidates_for_osengine(
    tickers: list[str],
    *,
    limit: int = _SCREENER_ENSURE_LIMIT,
) -> list[str]:
    """Prefer names that already have Day/ under Data/; otherwise keep board order capped."""
    cleaned = [str(t).strip().upper() for t in tickers if str(t or "").strip()]
    if not cleaned:
        return []
    data = list_osengine_day_tickers_from_data(limit=max(limit, _SCREENER_ENSURE_LIMIT))
    if data:
        data_set = set(data)
        intersected = [t for t in cleaned if t in data_set]
        if intersected:
            return intersected[:limit]
        return data[:limit]
    return cleaned[:limit]


async def ensure_osengine_d1_for_screener(
    db: Session,
    tickers: list[str],
    *,
    as_of: date,
    board: str = "TQBR",
    lookback_days: int = 14,
    run_id: int = 0,
    limit: int = _SCREENER_ENSURE_LIMIT,
) -> list[str]:
    """Download/import OsEngine D1 for screener candidates into candles_cache.

    Returns the (possibly narrowed) ticker list that was requested.
    """
    candidates = narrow_screener_candidates_for_osengine(tickers, limit=limit)
    if not candidates:
        return []

    from_date = as_of - timedelta(days=max(1, int(lookback_days)))
    till_date = as_of + timedelta(days=1)
    try:
        from app.modules.osengine import build_candle_ensure_request, get_osengine_facade

        facade = get_osengine_facade()
        req = build_candle_ensure_request(
            run_id=int(run_id or 0),
            tickers=candidates,
            interval="D1",
            from_date=from_date,
            till_date=till_date,
            board=(board or "TQBR").strip().upper() or "TQBR",
        )
        stats = await facade.ensure_candles_for_backtest(db, req)
        try:
            db.commit()
        except Exception:
            db.rollback()
        logger.info(
            "osengine screener ensure D1 as_of=%s board=%s candidates=%s hits=%s gaps=%s candles=%s err=%s",
            as_of.isoformat(),
            board,
            len(candidates),
            getattr(stats, "cache_full_hits", 0),
            getattr(stats, "instruments_with_gaps", 0),
            getattr(stats, "fetched_candles", 0),
            getattr(stats, "last_error", None),
        )
    except Exception:
        logger.exception(
            "osengine screener ensure D1 failed as_of=%s board=%s n=%s",
            as_of.isoformat(),
            board,
            len(candidates),
        )
    return candidates
