"""P2 price-window candles for glass-box overlay (SPEC-03 §6.4 / [R-12])."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.robots_v2.backtest.candle_io import load_candles_by_symbol_from_cache
from app.modules.trading_core.intervals import resolve_strategy_interval


def _parse_around(raw: datetime | str) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def resolve_run_market_and_interval(config_snapshot: dict[str, Any] | None) -> tuple[str, Any, str]:
    """Return (cache_market, resolved_interval, interval_raw) from run config."""
    from app.modules.robots_v2.backtest.service import v4_timeframe_to_interval_raw

    cfg = config_snapshot if isinstance(config_snapshot, dict) else {}
    core = cfg.get("core") if isinstance(cfg.get("core"), dict) else {}
    strategy = cfg.get("strategy") if isinstance(cfg.get("strategy"), dict) else {}
    instrument_type = str(core.get("instrumentType") or core.get("instrument_type") or "stock")
    timeframe = str(strategy.get("timeframe") or "5m")
    interval_raw = v4_timeframe_to_interval_raw(timeframe)
    resolved = resolve_strategy_interval(interval_raw)
    if instrument_type in ("perpetual", "coin_futures"):
        market = "bybit"
    else:
        market = (settings.OSENGINE_MARKET_KEY or "osengine").strip() or "osengine"
    return market, resolved, interval_raw


def fetch_price_window(
    db: Session,
    *,
    config_snapshot: dict[str, Any] | None,
    ticker: str,
    around: datetime | str,
    bars: int = 50,
) -> dict[str, Any]:
    """Load OHLCV around a decision timestamp from the market candle cache.

    ``bars`` is the half-window size (bars before and after ``around``), capped at 200.
    """
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return {
            "ticker": "",
            "around": None,
            "bars": 0,
            "interval": None,
            "market": None,
            "candles": [],
            "source": "cache",
            "gap": "ticker_required",
        }

    half = max(1, min(int(bars or 50), 200))
    around_dt = _parse_around(around)
    market, resolved, interval_raw = resolve_run_market_and_interval(config_snapshot)

    # code_num is usually minutes; special MOEX day/week/month codes differ.
    code_num = int(getattr(resolved, "code_num", 0) or 0)
    if code_num == 24:
        minutes = 1440
    elif code_num in (7, 31, 4):
        minutes = 1440 * max(1, code_num)
    else:
        minutes = max(1, code_num or 60)
    pad = timedelta(minutes=minutes * (half + 2))
    from_dt = around_dt - pad
    to_dt_exclusive = around_dt + pad + timedelta(minutes=max(1, minutes))

    try:
        raw = load_candles_by_symbol_from_cache(
            db,
            symbols=[symbol],
            interval_code=resolved.cache_label,
            interval_code_num=resolved.code_num,
            from_dt=from_dt,
            to_dt_exclusive=to_dt_exclusive,
            market=market,
        )
    except Exception:
        return {
            "ticker": symbol,
            "around": around_dt.isoformat(),
            "bars": half,
            "interval": interval_raw,
            "market": market,
            "candles": [],
            "source": "cache",
            "gap": "candle_source_error",
        }

    series = list(raw.get(symbol) or [])
    if not series:
        return {
            "ticker": symbol,
            "around": around_dt.isoformat(),
            "bars": half,
            "interval": interval_raw,
            "market": market,
            "candles": [],
            "source": "cache",
            "gap": f"no_candles_for_market:{market}",
        }

    # Pick nearest index to around, then slice ±half bars.
    def _row_time(row: dict[str, Any]) -> datetime:
        return _parse_around(row.get("time") or around_dt)

    times = [_row_time(r) for r in series]
    nearest = min(range(len(times)), key=lambda i: abs((times[i] - around_dt).total_seconds()))
    lo = max(0, nearest - half)
    hi = min(len(series), nearest + half + 1)
    window = series[lo:hi]

    candles: list[dict[str, Any]] = []
    for row in window:
        o = row.get("open")
        h = row.get("high")
        l = row.get("low")
        c = row.get("close")

        def _num(v: Any) -> float:
            if isinstance(v, dict):
                return float(v.get("units") or 0) + float(v.get("nano") or 0) / 1_000_000_000
            return float(v or 0)

        candles.append({
            "time": row.get("time"),
            "open": _num(o),
            "high": _num(h),
            "low": _num(l),
            "close": _num(c),
            "volume": int(row.get("volume") or 0),
        })

    return {
        "ticker": symbol,
        "around": around_dt.isoformat(),
        "bars": half,
        "interval": interval_raw,
        "market": market,
        "candles": candles,
        "source": "cache",
        "gap": None,
    }
