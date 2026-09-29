"""Daily universe snapshots from OsEngine Day candles → market_snapshot_*_history.

TEMP: replaces MOEX ISS board snapshots for history-backtest scoring.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)


def _next_pk(db: Session, table_name: str) -> int:
    seq_name = db.execute(
        text("SELECT pg_get_serial_sequence(:tbl, 'id')"),
        {"tbl": table_name},
    ).scalar()
    if seq_name:
        try:
            return int(db.execute(text("SELECT nextval(:seq)"), {"seq": seq_name}).scalar())
        except Exception:
            pass
    mx = db.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table_name}")).scalar()
    return int(mx or 0) + 1


def _list_board_tickers(db: Session, board: str, *, limit: int = 400) -> List[str]:
    from app.modules.robots.moex_securities_updater import queries as moex_q

    sql, params = moex_q.build_equity_universe_query(board=board, active_only=True)
    rows = db.execute(text(sql), params).fetchall()
    tickers = sorted({str(r[0]).strip().upper() for r in rows if r and r[0]})
    if tickers:
        return tickers[:limit]
    # Fallback: whatever Day candles already exist under market=osengine
    market = (settings.OSENGINE_MARKET_KEY or "osengine").strip() or "osengine"
    rows = db.execute(
        text(
            """
            SELECT DISTINCT UPPER(instrument_id) AS ticker
            FROM candles_cache
            WHERE market = :market AND interval = 'D1'
            ORDER BY ticker
            LIMIT :lim
            """
        ),
        {"market": market, "lim": limit},
    ).fetchall()
    return [str(r[0]) for r in rows if r and r[0]]


def _rows_from_day_candles(
    db: Session,
    *,
    day: date,
    board: str,
    tickers: List[str],
) -> List[Dict[str, Any]]:
    if not tickers:
        return []
    market = (settings.OSENGINE_MARKET_KEY or "osengine").strip() or "osengine"
    tz_name = (getattr(settings, "OSENGINE_CANDLE_TZ", None) or "Europe/Moscow").strip()
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    day_start_local = datetime.combine(day, time.min, tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)
    from_utc = day_start_local.astimezone(timezone.utc)
    to_utc = day_end_local.astimezone(timezone.utc)

    rows = db.execute(
        text(
            """
            SELECT instrument_id, ticker, open, high, low, close, volume
            FROM candles_cache
            WHERE market = :market
              AND interval = 'D1'
              AND instrument_id = ANY(:ids)
              AND candle_time >= :from_dt
              AND candle_time < :to_dt
            """
        ),
        {
            "market": market,
            "ids": [t.upper() for t in tickers],
            "from_dt": from_utc,
            "to_dt": to_utc,
        },
    ).mappings().all()

    out: List[Dict[str, Any]] = []
    for r in rows:
        ticker = str(r.get("instrument_id") or r.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        o = float(r["open"]) if r.get("open") is not None else None
        h = float(r["high"]) if r.get("high") is not None else None
        low = float(r["low"]) if r.get("low") is not None else None
        c = float(r["close"]) if r.get("close") is not None else None
        vol = float(r["volume"]) if r.get("volume") is not None else 0.0
        value = (vol * c) if c is not None else None
        out.append(
            {
                "ticker": ticker,
                "last_price": c,
                "open_price": o,
                "high_price": h,
                "low_price": low,
                "close_price": c,
                "prev_price": None,
                "volume_lots": vol,
                "value_today": value,
                "bid": None,
                "ask": None,
                "spread": None,
                "security_status": None,
                "trading_status": "OsEngine",
                "num_trades": None,
                "min_step": None,
                "issue_size": None,
                "board_id": board,
                "short_name": ticker,
                "isin": None,
                "lot_size": None,
                "prev_legal_close_price": None,
                "raw_payload": {"source": "osengine_d1", "board": board, "day": day.isoformat()},
            }
        )
    return out


def _insert_snapshot(
    db: Session,
    *,
    day: date,
    board: str,
    rows: List[Dict[str, Any]],
) -> int:
    day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    snapshot_id = _next_pk(db, "market_snapshot_history")
    now_utc = datetime.now(timezone.utc)
    db.execute(
        text(
            """
            INSERT INTO market_snapshot_history
            (id, snapshot_time, board, status, is_manual, ttl_minutes, created_at)
            VALUES (:id, :snapshot_time, :board, 'SUCCESS', TRUE, 0, :created_at)
            """
        ),
        {"id": snapshot_id, "snapshot_time": day_start, "board": board, "created_at": now_utc},
    )
    next_data_id = _next_pk(db, "market_snapshot_data_history")
    for i, r in enumerate(rows):
        rid = next_data_id + i
        raw = dict(r.get("raw_payload") or {})
        db.execute(
            text(
                """
                INSERT INTO market_snapshot_data_history
                (id, snapshot_id, ticker, last_price, open_price, prev_price, volume_today, value_today, volume_lots,
                 bid, ask, spread, security_status, trading_status, num_trades, min_step, issue_size, board_id,
                 short_name, low_price, high_price, close_price, value, isin, lot_size, prev_legal_close_price,
                 securities_payload, marketdata_payload)
                VALUES
                (:id, :snapshot_id, :ticker, :last_price, :open_price, :prev_price, :volume_today, :value_today, :volume_lots,
                 :bid, :ask, :spread, :security_status, :trading_status, :num_trades, :min_step, :issue_size, :board_id,
                 :short_name, :low_price, :high_price, :close_price, :value, :isin, :lot_size, :prev_legal_close_price,
                 CAST(:securities_payload AS jsonb), CAST(:marketdata_payload AS jsonb))
                """
            ),
            {
                "id": rid,
                "snapshot_id": snapshot_id,
                "ticker": str(r.get("ticker") or "").upper(),
                "last_price": r.get("last_price"),
                "open_price": r.get("open_price"),
                "prev_price": r.get("prev_price"),
                "volume_today": r.get("volume_lots"),
                "value_today": r.get("value_today"),
                "volume_lots": r.get("volume_lots"),
                "bid": r.get("bid"),
                "ask": r.get("ask"),
                "spread": r.get("spread"),
                "security_status": r.get("security_status"),
                "trading_status": r.get("trading_status"),
                "num_trades": r.get("num_trades"),
                "min_step": r.get("min_step"),
                "issue_size": r.get("issue_size"),
                "board_id": r.get("board_id"),
                "short_name": r.get("short_name"),
                "low_price": r.get("low_price"),
                "high_price": r.get("high_price"),
                "close_price": r.get("close_price") if r.get("close_price") is not None else r.get("last_price"),
                "value": r.get("value_today"),
                "isin": r.get("isin"),
                "lot_size": r.get("lot_size"),
                "prev_legal_close_price": r.get("prev_legal_close_price"),
                "securities_payload": json.dumps(raw, ensure_ascii=False),
                "marketdata_payload": json.dumps(raw, ensure_ascii=False),
            },
        )
    db.commit()
    return snapshot_id


async def ensure_daily_snapshot_from_osengine(
    db: Session,
    *,
    day: date,
    board: str = "TQBR",
    user_id: Optional[int] = None,
    run_id: Optional[int] = None,
) -> Optional[int]:
    """DB-first snapshot; gaps filled via OsEngine Day candles (MCP → Data/ → cache)."""
    from app.modules.trading_core.cancel import is_backtest_cancelled

    board_u = (board or "TQBR").strip().upper() or "TQBR"
    min_rows_for_reuse = 1
    day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    day_end_exclusive = day_start + timedelta(days=1)

    existing = db.execute(
        text(
            """
            SELECT h.id,
                   (SELECT COUNT(*) FROM market_snapshot_data_history d WHERE d.snapshot_id = h.id) AS data_rows
            FROM market_snapshot_history h
            WHERE h.board=:board
              AND h.status='SUCCESS'
              AND h.snapshot_time >= :day_start
              AND h.snapshot_time < :day_end
            ORDER BY h.snapshot_time ASC
            LIMIT 1
            """
        ),
        {"board": board_u, "day_start": day_start, "day_end": day_end_exclusive},
    ).first()
    existing_id = int(existing[0]) if existing else None
    existing_rows = int(existing[1] or 0) if existing else 0

    if run_id is not None and is_backtest_cancelled(run_id):
        return None
    if existing_id and existing_rows >= min_rows_for_reuse:
        if run_id is not None:
            from app.modules.robots.backtest_progress import touch_backtest_progress_runtime

            touch_backtest_progress_runtime(run_id)
        logger.info(
            "osengine snapshot cache hit day=%s board=%s snapshot_id=%s rows=%s",
            day.isoformat(),
            board_u,
            existing_id,
            existing_rows,
        )
        return existing_id

    if existing_id:
        db.execute(
            text("DELETE FROM market_snapshot_data_history WHERE snapshot_id=:sid"),
            {"sid": existing_id},
        )
        db.execute(
            text("DELETE FROM market_snapshot_history WHERE id=:sid"),
            {"sid": existing_id},
        )
        db.commit()

    tickers = _list_board_tickers(db, board_u)
    if not tickers:
        logger.warning("osengine snapshot: no tickers for board=%s day=%s", board_u, day.isoformat())
        return None

    # Prefer tickers that already have Day files under OsEngine Data/ (avoid full TQBR MCP storm).
    try:
        from app.modules.osengine.file_index import find_candle_files, resolve_data_root
        from app.modules.osengine.types import InstrumentKey

        root = resolve_data_root()
        if root is not None:
            with_files = [
                t
                for t in tickers
                if find_candle_files(root, instrument=InstrumentKey(t, board_u), interval="D1", max_files=1)
            ]
            if with_files:
                logger.info(
                    "osengine snapshot: using %s/%s tickers with Day files under Data/",
                    len(with_files),
                    len(tickers),
                )
                tickers = with_files
    except Exception:
        logger.debug("osengine snapshot: Data/ filter skipped", exc_info=True)

    # Ensure Day candles for this calendar day via OsEngine (MCP + files).
    try:
        from app.modules.osengine import build_candle_ensure_request, get_osengine_facade

        facade = get_osengine_facade()
        req = build_candle_ensure_request(
            run_id=int(run_id or 0),
            tickers=tickers,
            interval="D1",
            from_date=day,
            till_date=day + timedelta(days=1),
            board=board_u,
        )
        await facade.ensure_candles_for_backtest(db, req)
        try:
            db.commit()
        except Exception:
            db.rollback()
    except Exception:
        logger.exception(
            "osengine snapshot ensure candles failed day=%s board=%s",
            day.isoformat(),
            board_u,
        )

    if run_id is not None and is_backtest_cancelled(run_id):
        return None

    rows = _rows_from_day_candles(db, day=day, board=board_u, tickers=tickers)
    if run_id is not None:
        from app.modules.robots.backtest_progress import touch_backtest_progress_runtime

        touch_backtest_progress_runtime(run_id)
    if not rows:
        logger.warning(
            "osengine snapshot empty day=%s board=%s tickers=%s (no D1 in candles_cache)",
            day.isoformat(),
            board_u,
            len(tickers),
        )
        return None

    sid = _insert_snapshot(db, day=day, board=board_u, rows=rows)
    logger.info(
        "osengine snapshot built day=%s board=%s snapshot_id=%s rows=%s",
        day.isoformat(),
        board_u,
        sid,
        len(rows),
    )
    return sid


__all__ = ["ensure_daily_snapshot_from_osengine"]
