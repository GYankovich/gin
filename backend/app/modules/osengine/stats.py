"""Статистика операций OsEngineFacade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from app.modules.osengine.types import TimeRange


@dataclass
class EnsureCandlesStats:
    run_id: int = 0
    interval: str = ""
    total_instruments: int = 0
    cache_full_hits: int = 0
    instruments_with_gaps: int = 0
    fetched_ranges: int = 0
    fetched_candles: int = 0
    leases_created: int = 0
    skipped_provider_unavailable: bool = False
    cancelled: bool = False
    errors: int = 0
    last_error: str = ""
    gap_samples: List[TimeRange] = field(default_factory=list)

    def summary(self) -> str:
        tail = ""
        if self.errors:
            tail = f" errors={self.errors} last={self.last_error[:160]}"
        if self.skipped_provider_unavailable:
            tail += " provider=unavailable"
        return (
            f"osengine ensure interval={self.interval} run_id={self.run_id} "
            f"instruments={self.total_instruments} hits={self.cache_full_hits} "
            f"gaps={self.instruments_with_gaps} fetched_ranges={self.fetched_ranges} "
            f"candles={self.fetched_candles} leases={self.leases_created}{tail}"
        )


@dataclass
class LeaseReleaseStats:
    run_id: int = 0
    leases_touched: int = 0
    expires_at_iso: str = ""


@dataclass
class CacheGcStats:
    expired_leases: int = 0
    deleted_candle_rows: int = 0
    deleted_tick_rows: int = 0
    deleted_depth_rows: int = 0


@dataclass
class LiveIngestStatus:
    enabled: bool = False
    bridge_connected: bool = False
    subscribed_instruments: int = 0
    last_candle_at: str | None = None
    last_tick_at: str | None = None
    last_depth_at: str | None = None
    lag_seconds: float | None = None
    detail: str = "not wired"


__all__ = [
    "CacheGcStats",
    "EnsureCandlesStats",
    "LeaseReleaseStats",
    "LiveIngestStatus",
]
