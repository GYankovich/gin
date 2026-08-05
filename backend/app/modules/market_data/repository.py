#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesMarketDataRepository [1]
#/// Исходный модуль `backend/app/modules/market_data/repository.py` — автоматическая разметка для Obsidian Source Scanner.

from datetime import datetime
from typing import Any, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session


def upsert_instrument(
        db: Session,
        schema: str,
        figi: str,
        ticker: Optional[str] = None,
        name: Optional[str] = None,
        instrument_type: Optional[str] = None,
) -> None:
    sql = text(f"""
        INSERT INTO market_instruments (figi, ticker, name, instrument_type, updated_at)
        VALUES (:figi, :ticker, :name, :itype, CURRENT_TIMESTAMP)
        ON CONFLICT (figi) DO UPDATE SET
            ticker = COALESCE(EXCLUDED.ticker, market_instruments.ticker),
            name = COALESCE(EXCLUDED.name, market_instruments.name),
            instrument_type = COALESCE(EXCLUDED.instrument_type, market_instruments.instrument_type),
            updated_at = CURRENT_TIMESTAMP
    """)
    db.execute(sql, {
        "figi": figi,
        "ticker": ticker,
        "name": name,
        "itype": instrument_type,
    })


def upsert_candles_batch(db: Session, schema: str, rows: List[Tuple]) -> None:
    """rows: tuples (figi, interval, ts, o, h, l, c, vol)"""
    if not rows:
        return
    sql = text(f"""
        INSERT INTO market_candles
            (figi, candle_interval, candle_time, open, high, low, close, volume)
        VALUES
            (:figi, :interval, :ts, :o, :h, :l, :c, :vol)
        ON CONFLICT (figi, candle_interval, candle_time) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume
    """)
    for r in rows:
        figi, interval, ts, o, h, l, c, vol = r
        db.execute(sql, {
            "figi": figi,
            "interval": interval,
            "ts": ts,
            "o": o,
            "h": h,
            "l": l,
            "c": c,
            "vol": vol,
        })


def fetch_candles_range(
        db: Session,
        schema: str,
        figi: str,
        interval: str,
        from_dt: datetime,
        to_dt: datetime,
) -> List[Any]:
    sql = text(f"""
        SELECT candle_time, open, high, low, close, volume
        FROM market_candles
        WHERE figi = :figi
          AND candle_interval = :interval
          AND candle_time >= :from_dt
          AND candle_time <= :to_dt
        ORDER BY candle_time ASC
    """)
    return db.execute(sql, {
        "figi": figi,
        "interval": interval,
        "from_dt": from_dt,
        "to_dt": to_dt,
    }).fetchall()


def count_candles_in_range(
        db: Session,
        schema: str,
        figi: str,
        interval: str,
        from_dt: datetime,
        to_dt: datetime,
) -> int:
    sql = text(f"""
        SELECT COUNT(*)::bigint
        FROM market_candles
        WHERE figi = :figi
          AND candle_interval = :interval
          AND candle_time >= :from_dt
          AND candle_time <= :to_dt
    """)
    row = db.execute(sql, {
        "figi": figi,
        "interval": interval,
        "from_dt": from_dt,
        "to_dt": to_dt,
    }).scalar()
    return int(row or 0)


def fetch_coverage_bounds(
        db: Session,
        schema: str,
        figi: str,
        interval: str,
) -> Optional[Tuple[datetime, datetime]]:
    sql = text(f"""
        SELECT MIN(candle_time), MAX(candle_time)
        FROM market_candles
        WHERE figi = :figi AND candle_interval = :interval
    """)
    row = db.execute(sql, {"figi": figi, "interval": interval}).first()
    if not row or row[0] is None:
        return None
    return row[0], row[1]


def list_instruments_with_data(db: Session, schema: str) -> List[Any]:
    sql = text(f"""
        SELECT DISTINCT c.figi,
               i.ticker,
               i.name,
               i.instrument_type,
               c.candle_interval,
               MIN(c.candle_time) AS first_ts,
               MAX(c.candle_time) AS last_ts,
               COUNT(*)::bigint AS candle_count
        FROM market_candles c
        LEFT JOIN market_instruments i ON i.figi = c.figi
        GROUP BY c.figi, i.ticker, i.name, i.instrument_type, c.candle_interval
        ORDER BY c.figi, c.candle_interval
    """)
    return db.execute(sql).fetchall()


def insert_backtest(
        db: Session,
        schema: str,
        user_id: int,
        name: Optional[str],
        figi: str,
        candle_interval: str,
        strategy: str,
        from_dt: datetime,
        to_dt: datetime,
        initial_capital: float,
        request_payload: dict,
        result_payload: dict,
):
    sql = text(f"""
        INSERT INTO market_backtests
            (user_id, name, figi, candle_interval, strategy, from_date, to_date, initial_capital, request_payload, result_payload)
        VALUES
            (:user_id, :name, :figi, :interval, :strategy, :from_dt, :to_dt, :initial_capital, :request_payload, :result_payload)
        RETURNING id
    """)
    return db.execute(sql, {
        "user_id": user_id,
        "name": name,
        "figi": figi,
        "interval": candle_interval,
        "strategy": strategy,
        "from_dt": from_dt,
        "to_dt": to_dt,
        "initial_capital": initial_capital,
        "request_payload": request_payload,
        "result_payload": result_payload,
    }).scalar()


def list_backtests(db: Session, schema: str, user_id: int, limit: int = 50) -> List[Any]:
    sql = text(f"""
        SELECT id, user_id, name, figi, candle_interval, strategy, from_date, to_date,
               initial_capital, request_payload, result_payload, created_at
        FROM market_backtests
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    return db.execute(sql, {"user_id": user_id, "limit": limit}).fetchall()


def get_instrument_ticker(db: Session, schema: str, figi: str) -> Optional[str]:
    sql = text(f"""
        SELECT ticker
        FROM market_instruments
        WHERE figi = :figi
        LIMIT 1
    """)
    row = db.execute(sql, {"figi": figi}).first()
    return row[0] if row and row[0] else None
