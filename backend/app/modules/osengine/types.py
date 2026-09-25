"""Типы границ OsEngineFacade: окна, lease, ключ инструмента."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Optional

LeaseStatus = Literal["active", "cooling", "expired"]
StreamKind = Literal["candles", "ticks", "depth"]


@dataclass(frozen=True, slots=True)
class InstrumentKey:
    """Стабильный ключ бумаги в кэше OsEngine."""

    ticker: str
    board: str = "TQBR"

    def normalized(self) -> "InstrumentKey":
        return InstrumentKey(
            ticker=(self.ticker or "").strip().upper(),
            board=(self.board or "TQBR").strip().upper() or "TQBR",
        )

    @property
    def cache_id(self) -> str:
        """Ключ в candles_cache.instrument_id — тикер (как у MOEX-пути)."""
        return self.normalized().ticker

    @property
    def osengine_security_id(self) -> str:
        """Идентификатор для файлов/bridge OsEngine: BOARD:TICKER."""
        k = self.normalized()
        return f"{k.board}:{k.ticker}"


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Полуинтервал [start, end) в UTC-датах/времени бэктеста."""

    start: date
    end: date

    def normalized(self) -> "TimeRange":
        if self.end < self.start:
            raise ValueError("TimeRange.end must be >= start")
        return TimeRange(start=self.start, end=self.end)

    def overlaps(self, other: "TimeRange") -> bool:
        a, b = self.normalized(), other.normalized()
        return a.start < b.end and b.start < a.end


@dataclass(frozen=True, slots=True)
class CandleEnsureRequest:
    run_id: int
    instruments: tuple[InstrumentKey, ...]
    interval: str
    window: TimeRange
    lookback_days: int = 0


@dataclass(frozen=True, slots=True)
class CacheLease:
    id: Optional[int]
    run_id: int
    market: str
    instrument_id: str
    interval: str
    from_date: date
    to_date: date
    status: LeaseStatus
    expires_at: Optional[datetime] = None


__all__ = [
    "CacheLease",
    "CandleEnsureRequest",
    "InstrumentKey",
    "LeaseStatus",
    "StreamKind",
    "TimeRange",
]
