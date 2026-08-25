"""Historical liquidity metrics from candles_cache (backtest scoring, no look-ahead)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.robots.trading.data.providers.db_cache import query_candles_cache_rows


def volume_lookback_days(config: Dict[str, Any], default: int = 14) -> int:
    hs = config.get("historical_screening") if isinstance(config.get("historical_screening"), dict) else {}
    pipe = config.get("pipeline") if isinstance(config.get("pipeline"), dict) else {}
    for raw in (hs.get("lookback_days"), pipe.get("volume_lookback_days")):
        try:
            if raw is not None:
                return max(1, int(raw))
        except (TypeError, ValueError):
            pass
    return default


def _day_start_utc(d: date) -> datetime:
    return datetime.combine(d, time.min).replace(tzinfo=timezone.utc)


def avg_daily_value_rub_from_candles(
    db: Session,
    *,
    ticker: str,
    as_of_date: date,
    lookback_days: int,
    market: str = "moex",
) -> Optional[float]:
    """Mean daily turnover (close * volume) over [as_of - lookback, as_of)."""
    end = _day_start_utc(as_of_date)
    start = end - timedelta(days=max(1, int(lookback_days)))
    rows = query_candles_cache_rows(
        db,
        market=market,
        ticker=str(ticker or "").upper(),
        interval_code="D1",
        interval_code_num=24,
        from_dt=start,
        to_dt_exclusive=end,
    )
    if not rows:
        return None
    values: List[float] = []
    for row in rows:
        close = float(row.get("close") or 0)
        volume = float(row.get("volume") or 0)
        if close > 0 and volume > 0:
            values.append(close * volume)
    if not values:
        return None
    return sum(values) / len(values)


def point_in_time_metrics(
    db: Session,
    *,
    tickers: list[str],
    as_of_date: date,
    lookback_days: int = 14,
    market: str = "moex",
) -> dict[str, dict[str, float]]:
    """Last close and mean daily turnover using only candles strictly before as_of_date."""
    from app.modules.robots.trading.data.providers.db_cache import query_candles_cache_rows_bulk

    ids = [str(t).upper() for t in tickers if t]
    if not ids:
        return {}
    end = _day_start_utc(as_of_date)
    start = end - timedelta(days=max(1, int(lookback_days)))
    grouped = query_candles_cache_rows_bulk(
        db,
        market=market,
        instrument_ids=ids,
        interval_code="D1",
        interval_code_num=24,
        from_dt=start,
        to_dt_exclusive=end,
    )
    out: dict[str, dict[str, float]] = {}
    for ticker, rows in grouped.items():
        values: list[float] = []
        last_close = 0.0
        for row in rows:
            close = float(row.get("close") or 0)
            volume = float(row.get("volume") or 0)
            if close <= 0:
                continue
            last_close = close
            if volume > 0:
                values.append(close * volume)
        if last_close <= 0:
            continue
        out[str(ticker).upper()] = {
            "last_close": last_close,
            "avg_value": (sum(values) / len(values)) if values else 0.0,
        }
    return out


def enrich_moex_snapshot_rows_historical_liquidity(
    db: Session,
    *,
    rows: List[Dict[str, Any]],
    as_of_date: date,
    lookback_days: int,
) -> None:
    """Mutate snapshot rows: replace value_today with historical avg for volume/turnover filters."""
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        avg_val = avg_daily_value_rub_from_candles(
            db,
            ticker=ticker,
            as_of_date=as_of_date,
            lookback_days=lookback_days,
            market="moex",
        )
        if avg_val is not None:
            row["historical_avg_volume_rub"] = avg_val
            row["value_today"] = avg_val


def list_bybit_symbols_from_cache(db: Session) -> List[str]:
    from app.modules.robots.trading.pipeline.bybit_symbol_filter import filter_backtest_universe_symbols

    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT instrument_id
            FROM candles_cache
            WHERE LOWER(market) = 'bybit'
              AND interval IN ('D1', 'I24', '1d', '1D', 'CANDLE_INTERVAL_DAY')
            ORDER BY instrument_id
            """
        )
    ).fetchall()
    raw = sorted({str(r[0]).strip().upper() for r in rows if r and r[0]})
    return filter_backtest_universe_symbols(raw)


def crypto_metrics_as_of_date(
    db: Session,
    *,
    symbol: str,
    trade_date: date,
    lookback_days: int = 7,
    instrument_category: str = "linear",
    funding_lookback_hours: int = 8,
    atr_period: int = 14,
    include_derivatives: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Point-in-time crypto liquidity from D1 candles_cache (no live API).

    Uses last completed day before trade_date for turnover24h; daily range (H-L)/close
    as ``dailyRangePercent`` (not bid-ask spread).
    Optionally enriches with funding/OI/LSR from DB and RVOL/ATR from candles.
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None
    end = _day_start_utc(trade_date)
    start = end - timedelta(days=max(1, int(lookback_days)))
    rows = query_candles_cache_rows(
        db,
        market="bybit",
        ticker=sym,
        interval_code="D1",
        interval_code_num=24,
        from_dt=start,
        to_dt_exclusive=end,
    )
    if not rows:
        return None

    turnovers: List[float] = []
    spreads: List[float] = []
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    volumes: List[float] = []
    last_close: Optional[float] = None
    for row in rows:
        close = float(row.get("close") or 0)
        volume = float(row.get("volume") or 0)
        high = float(row.get("high") or close or 0)
        low = float(row.get("low") or close or 0)
        if close <= 0:
            continue
        turnovers.append(volume * close)
        volumes.append(volume)
        highs.append(high)
        lows.append(low)
        closes.append(close)
        if high > 0 and low > 0:
            spreads.append((high - low) / close * 100.0)
        last_close = close

    if not turnovers or last_close is None:
        return None

    turnover24h = turnovers[-1]
    daily_range_pct = spreads[-1] if spreads else None
    if daily_range_pct is None and len(spreads) > 0:
        daily_range_pct = sum(spreads) / len(spreads)

    from app.modules.robots.crypto_universe_metrics import compute_atr_percent, compute_rvol

    metrics: Dict[str, Any] = {
        "symbol": sym,
        "turnover24h": turnover24h,
        "lastPrice": last_close,
        "dailyRangePercent": daily_range_pct,
        "rvol": compute_rvol(volumes),
        "atr_percent": compute_atr_percent(highs, lows, closes, period=atr_period),
    }

    if include_derivatives:
        from app.modules.robots.crypto_universe import (
            load_historical_funding_avg,
            load_historical_lsr,
            load_historical_oi_usd,
        )

        as_of = end
        metrics["avg_funding_rate"] = load_historical_funding_avg(
            db,
            symbol=sym,
            as_of=as_of,
            instrument_category=instrument_category,
            lookback_hours=funding_lookback_hours,
        )
        metrics["open_interest_usd"] = load_historical_oi_usd(
            db,
            symbol=sym,
            as_of=as_of,
            instrument_category=instrument_category,
        )
        metrics["lsr"] = load_historical_lsr(
            db,
            symbol=sym,
            as_of=as_of,
            instrument_category=instrument_category,
        )

    return metrics
