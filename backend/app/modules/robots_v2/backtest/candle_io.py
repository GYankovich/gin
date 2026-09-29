"""Candle cache load + Bybit prefetch for robots_v2 backtest (moved off TradingOrchestrator)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.modules.trading_core.data import CandlePrefetchStats
from app.modules.trading_core.intervals import ResolvedInterval


def _cache_row_to_candle_dict(row: Any) -> Dict[str, Any]:
    close = float(row["close"] or 0)
    units = int(close)
    nano = int(round((close - units) * 1_000_000_000))
    ct = row["candle_time"]
    time_iso = ct.isoformat() if hasattr(ct, "isoformat") else str(ct or "")
    return {
        "time": time_iso,
        "open": {"units": int(float(row["open"] or 0)), "nano": 0},
        "high": {"units": int(float(row["high"] or 0)), "nano": 0},
        "low": {"units": int(float(row["low"] or 0)), "nano": 0},
        "close": {"units": units, "nano": nano},
        "volume": int(row["volume"] or 0),
    }


def load_candles_by_symbol_from_cache(
    db: Session,
    *,
    symbols: List[str],
    interval_code: str,
    interval_code_num: int,
    from_dt: datetime,
    to_dt_exclusive: datetime,
    market: str = "bybit",
    batch_size: int = 200,
) -> Dict[str, List[Dict[str, Any]]]:
    from app.modules.trading_core.data import get_market_data_facade

    market_data = get_market_data_facade()
    normalized = [str(raw or "").strip().upper() for raw in symbols if str(raw or "").strip()]
    if not normalized:
        return {}

    bulk_rows = market_data.read_candles_cache_rows_bulk(
        db,
        market=market,
        instrument_ids=normalized,
        interval_code=interval_code,
        interval_code_num=interval_code_num,
        from_dt=from_dt,
        to_dt_exclusive=to_dt_exclusive,
        batch_size=batch_size,
    )
    out: Dict[str, List[Dict[str, Any]]] = {}
    for symbol in normalized:
        rows = bulk_rows.get(symbol) or []
        if rows:
            out[symbol] = [_cache_row_to_candle_dict(r) for r in rows]
    return out


async def prefetch_crypto_candles_for_replay(
    db: Session,
    *,
    symbols: List[str],
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
    load_cached_candles: bool = False,
) -> tuple[CandlePrefetchStats, Dict[str, List[Dict[str, Any]]]]:
    """ByBit historical kline prefetch (market=bybit) → candles_cache."""
    from app.modules.trading_core.data.providers.bybit_market import ensure_candles_bybit_market

    stats = await ensure_candles_bybit_market(
        db,
        symbols=symbols,
        resolved=resolved,
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
    if not load_cached_candles:
        return stats, {}

    from_dt = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
    to_dt_exclusive = datetime.combine(till_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    candles_by_symbol = load_candles_by_symbol_from_cache(
        db,
        symbols=list(symbols),
        interval_code=resolved.cache_label,
        interval_code_num=resolved.code_num,
        from_dt=from_dt,
        to_dt_exclusive=to_dt_exclusive,
    )
    return stats, candles_by_symbol
