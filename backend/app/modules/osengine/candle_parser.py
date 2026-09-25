"""Парсер строк свечей OsEngine (Candle.StringToSave / SetCandleFromString)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

# Формат: yyyyMMdd,HHmmss,open,high,low,close,volume[,openInterest]


@dataclass(frozen=True, slots=True)
class ParsedCandle:
    time_start: datetime  # UTC
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    open_interest: Optional[Decimal] = None


def _parse_decimal(raw: str) -> Decimal:
    s = (raw or "").strip().replace(",", ".")
    if not s:
        raise InvalidOperation("empty")
    return Decimal(s)


def parse_candle_line(
    line: str,
    *,
    source_tz: str = "Europe/Moscow",
) -> Optional[ParsedCandle]:
    """Парсит одну CSV-строку OsEngine. Битые строки → None."""
    text = (line or "").strip()
    if not text or text.startswith("#"):
        return None
    parts = text.split(",")
    if len(parts) < 6:
        return None
    date_s = parts[0].strip()
    time_s = parts[1].strip()
    if len(date_s) != 8 or len(time_s) < 1:
        return None
    try:
        # HHmmss; допускаем Hhmmss без leading zeros на часах редко — OsEngine пишет 6 цифр
        ts_local = datetime.strptime(f"{date_s}{time_s.zfill(6)[:6]}", "%Y%m%d%H%M%S")
        tz = ZoneInfo(source_tz)
        ts_utc = ts_local.replace(tzinfo=tz).astimezone(timezone.utc)
        o = _parse_decimal(parts[2])
        h = _parse_decimal(parts[3])
        l = _parse_decimal(parts[4])
        c = _parse_decimal(parts[5])
        vol = Decimal("1")
        if len(parts) > 6 and parts[6].strip():
            try:
                vol = _parse_decimal(parts[6])
            except InvalidOperation:
                vol = Decimal("1")
        oi: Optional[Decimal] = None
        if len(parts) > 7 and parts[7].strip():
            try:
                oi = _parse_decimal(parts[7])
            except InvalidOperation:
                oi = None
        return ParsedCandle(
            time_start=ts_utc,
            open=o,
            high=h,
            low=l,
            close=c,
            volume=vol,
            open_interest=oi,
        )
    except (ValueError, InvalidOperation, OSError):
        return None


def iter_candles_from_file(
    path: str,
    *,
    source_tz: str = "Europe/Moscow",
    from_utc: Optional[datetime] = None,
    to_utc_exclusive: Optional[datetime] = None,
) -> Iterator[ParsedCandle]:
    """Стримит свечи из файла; фильтр по [from_utc, to_utc_exclusive) в UTC."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            candle = parse_candle_line(line, source_tz=source_tz)
            if candle is None:
                continue
            ts = candle.time_start
            if from_utc is not None and ts < from_utc:
                continue
            if to_utc_exclusive is not None and ts >= to_utc_exclusive:
                continue
            yield candle


__all__ = ["ParsedCandle", "iter_candles_from_file", "parse_candle_line"]
