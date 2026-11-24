"""Timeframe bar clock for the live/paper cycle.

Seeded history is a series of closed bars. The poll loop used to overwrite the
last bar's OHLC on every tick and call that a bar close. Entries for momentum
and reversion run only when the strategy timeframe actually rolls.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.trading_core.contracts import Candle
from app.modules.trading_core.intervals import bar_duration_seconds, resolve_strategy_interval

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MAX_BARS = 200
# MOEX ISS candle `begin` is Moscow wall time without an offset.
_MSK = timezone(timedelta(hours=3))


def interval_minutes(timeframe: str) -> int:
    resolved = resolve_strategy_interval(timeframe or "5m")
    return max(1, bar_duration_seconds(int(resolved.code_num)) // 60)


def floor_bar_open(ts: datetime, minutes: int) -> datetime:
    """UTC open of the bar that contains `ts`. Matches T-Invest candle times."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    ts = ts.replace(second=0, microsecond=0)
    step = max(int(minutes), 1)
    if step >= 24 * 60:
        return ts.replace(hour=0, minute=0)
    delta_min = int((ts - _EPOCH).total_seconds() // 60)
    bucket = (delta_min // step) * step
    return _EPOCH + timedelta(minutes=bucket)


def parse_moex_candle_begin(raw: object) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
    else:
        text = str(raw).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_MSK)
    return dt.astimezone(timezone.utc)


def series_needs_roll(
    histories: dict[str, list[Candle]],
    *,
    now: datetime,
    minutes: int,
    committed_open: datetime | None,
) -> bool:
    """True once per bar, when any series still ends on an older bar."""
    current = floor_bar_open(now, minutes)
    if committed_open is not None and floor_bar_open(committed_open, minutes) == current:
        return False
    for hist in histories.values():
        if not hist:
            continue
        if floor_bar_open(hist[-1].time, minutes) < current:
            return True
    return False


def closed_bars_ready(
    histories: dict[str, list[Candle]],
    *,
    forming_open: datetime,
    minutes: int,
) -> bool:
    """True when every non-empty series ends on a closed bar that has volume."""
    forming = floor_bar_open(forming_open, minutes)
    saw = False
    for hist in histories.values():
        if not hist:
            continue
        last = hist[-1]
        if floor_bar_open(last.time, minutes) >= forming:
            continue
        saw = True
        if int(last.volume or 0) <= 0:
            return False
    return saw


def merge_closed_candles(
    hist: list[Candle],
    incoming: list[Candle],
    *,
    forming_open: datetime,
    minutes: int,
) -> list[Candle]:
    """Keep closed bars only. Incoming OHLCV (with volume) replaces the same open."""
    forming = floor_bar_open(forming_open, minutes)
    by_open: dict[datetime, Candle] = {}
    for candle in hist:
        opened = floor_bar_open(candle.time, minutes)
        if opened >= forming:
            continue
        by_open[opened] = candle
    for candle in incoming:
        try:
            close = float(candle.close)
        except (TypeError, ValueError):
            continue
        if close <= 0:
            continue
        opened = floor_bar_open(candle.time, minutes)
        if opened >= forming:
            continue
        candle.time = opened
        by_open[opened] = candle
    merged = [by_open[key] for key in sorted(by_open)]
    return merged[-_MAX_BARS:]


def update_forming_bar(
    hist: list[Candle],
    *,
    price: float,
    now: datetime,
    minutes: int,
    timeframe: str,
    ticker: str,
) -> list[Candle]:
    """Move the in-progress bar. A closed bar already in history is left intact."""
    try:
        px = float(price)
    except (TypeError, ValueError):
        return hist
    if px <= 0:
        return hist
    current = floor_bar_open(now, minutes)
    if hist:
        last_open = floor_bar_open(hist[-1].time, minutes)
        if last_open == current:
            last = hist[-1]
            last.close = px
            last.high = max(float(last.high or px), px)
            last.low = min(float(last.low or px), px)
            return hist
        if last_open > current:
            return hist
    hist.append(Candle(
        interval=timeframe,
        time=current,
        open=px,
        high=px,
        low=px,
        close=px,
        volume=0,
        secid=ticker,
    ))
    if len(hist) > _MAX_BARS:
        return hist[-_MAX_BARS:]
    return hist
