"""Статистика prefetch/gap-fill свечей (BRD-ARCH-04)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CandlePrefetchStats:
    total_tickers: int = 0
    processed_tickers: int = 0
    cache_full_hits: int = 0
    fetched_tickers: int = 0
    fetched_ranges: int = 0
    fetched_candles: int = 0
    skipped_unsupported_interval: bool = False
    cancelled: bool = False
    api_errors: int = 0
    last_api_error: str = ""
    interval_label: str = ""
    moex_interval_code: int = 0

    def summary(self) -> str:
        if self.skipped_unsupported_interval:
            return f"prefetch skipped (MOEX interval {self.moex_interval_code} not supported)"
        tail = ""
        if self.api_errors:
            tail = f" api_errors={self.api_errors} last={self.last_api_error[:160]}"
        return (
            f"prefetch interval={self.interval_label} moex={self.moex_interval_code} "
            f"tickers={self.processed_tickers}/{self.total_tickers} "
            f"cache_hits={self.cache_full_hits} fetched={self.fetched_tickers} "
            f"ranges={self.fetched_ranges} candles={self.fetched_candles}{tail}"
        )


@dataclass
class FundingPrefetchStats:
    total_symbols: int = 0
    processed_symbols: int = 0
    cache_full_hits: int = 0
    fetched_symbols: int = 0
    fetched_rows: int = 0
    cancelled: bool = False
    api_errors: int = 0
    last_api_error: str = ""

    def summary(self) -> str:
        tail = ""
        if self.api_errors:
            tail = f" api_errors={self.api_errors} last={self.last_api_error[:160]}"
        return (
            f"funding prefetch symbols={self.processed_symbols}/{self.total_symbols} "
            f"cache_hits={self.cache_full_hits} fetched={self.fetched_symbols} "
            f"rows={self.fetched_rows}{tail}"
        )


@dataclass
class GapFillResult:
    attempted: bool = False
    success: bool = False
    row_count: int = 0


__all__ = ["CandlePrefetchStats", "FundingPrefetchStats", "GapFillResult"]
