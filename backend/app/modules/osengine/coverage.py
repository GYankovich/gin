"""Слияние покрытых окон и вычисление missing gaps для prefetch."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, List, Sequence, Tuple

from app.modules.osengine.types import TimeRange

DateRange = Tuple[date, date]


def merge_ranges(ranges: Iterable[TimeRange | DateRange]) -> List[TimeRange]:
    """Сливает пересекающиеся/стыкующиеся окна в минимальный набор."""
    normalized: List[TimeRange] = []
    for item in ranges:
        if isinstance(item, TimeRange):
            r = item.normalized()
        else:
            start, end = item
            r = TimeRange(start=start, end=end).normalized()
        if r.start == r.end:
            continue
        normalized.append(r)
    if not normalized:
        return []
    normalized.sort(key=lambda x: (x.start, x.end))
    merged: List[TimeRange] = [normalized[0]]
    for cur in normalized[1:]:
        last = merged[-1]
        # стык end==start тоже сливаем (непрерывное покрытие)
        if cur.start <= last.end:
            if cur.end > last.end:
                merged[-1] = TimeRange(start=last.start, end=cur.end)
        else:
            merged.append(cur)
    return merged


def missing_ranges(needed: TimeRange, covered: Sequence[TimeRange | DateRange]) -> List[TimeRange]:
    """Возвращает части needed, не покрытые covered (после merge)."""
    need = needed.normalized()
    if need.start == need.end:
        return []
    parts = merge_ranges(covered)
    gaps: List[TimeRange] = []
    cursor = need.start
    for part in parts:
        if part.end <= cursor:
            continue
        if part.start > need.end:
            break
        if part.start > cursor:
            gap_end = min(part.start, need.end)
            if gap_end > cursor:
                gaps.append(TimeRange(start=cursor, end=gap_end))
        cursor = max(cursor, min(part.end, need.end))
        if cursor >= need.end:
            break
    if cursor < need.end:
        gaps.append(TimeRange(start=cursor, end=need.end))
    return gaps


def expand_lookback(window: TimeRange, lookback_days: int) -> TimeRange:
    days = max(0, int(lookback_days))
    w = window.normalized()
    if days <= 0:
        return w
    return TimeRange(start=w.start - timedelta(days=days), end=w.end)


__all__ = ["DateRange", "expand_lookback", "merge_ranges", "missing_ranges"]
