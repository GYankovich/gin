"""Диапазоны времени без баров в кеше → подзапросы к MOEX только по «дырам» [ref: ARCH-01]."""
from __future__ import annotations

import bisect
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Sequence, Tuple

from app.modules.market_data_v1.intervals import CANONICAL_TO_MOEX


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def bar_timedelta(canonical_interval: str) -> timedelta:
    """Номинальный шаг ряда по каноническому interval (для эвристики, не календарь MOEX)."""
    c = (canonical_interval or "").strip()
    if c not in CANONICAL_TO_MOEX:
        raise ValueError(f"unknown interval: {canonical_interval}")
    if c == "1m":
        return timedelta(minutes=1)
    if c == "10m":
        return timedelta(minutes=10)
    if c == "1h":
        return timedelta(hours=1)
    if c == "1d":
        return timedelta(days=1)
    if c == "1w":
        return timedelta(days=7)
    if c == "1M":
        return timedelta(days=31)
    return timedelta(days=1)


def internal_gap_threshold(canonical_interval: str) -> timedelta:
    """
    Минимальный разрыв между двумя соседними bucket_start в кеше, после которого
    считаем, что между ними есть «дыра» и нужен дозапрос MOEX.

    Для дневок допускаем выходные (Fri→Mon < порога), но ловим пропущенные недели и т.п.
    """
    c = (canonical_interval or "").strip()
    if c == "1m":
        return timedelta(minutes=5)
    if c == "10m":
        return timedelta(minutes=35)
    if c == "1h":
        return timedelta(hours=3)
    if c == "1d":
        return timedelta(days=5)
    if c == "1w":
        return timedelta(days=14)
    if c == "1M":
        return timedelta(days=62)
    return timedelta(days=5)


def merge_ranges(ranges: Sequence[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    """Объединяет только пересекающиеся отрезки [start, end]; смыкание в одной точке не сливаем (иначе окно job вырождается в один полный fetch)."""
    if not ranges:
        return []
    ordered = sorted((a, b) for a, b in ranges if a < b)
    out: List[Tuple[datetime, datetime]] = [ordered[0]]
    for a, b in ordered[1:]:
        la, lb = out[-1]
        if a < lb:
            out[-1] = (la, max(lb, b))
        else:
            out.append((a, b))
    return out


def count_weekdays_in_date_range(d0: date, d1: date) -> int:
    """Число дней пн–пт на отрезке календарных дат [d0, d1] включительно."""
    if d1 < d0:
        return 0
    n = 0
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


# Верхняя оценка баров на один будний день (TQBR, основная сессия; праздники/укороченные не вычитаем).
_BARS_PER_WEEKDAY_UPPER: dict[str, float] = {
    "1m": 520.0,
    "10m": 52.0,
    "1h": 10.0,
    "1d": 1.0,
    "1w": 0.25,
    "1M": 0.05,
}


def expected_bar_count_upper_bound(
        from_ts: datetime,
        to_ts: datetime,
        canonical_interval: str,
) -> int:
    """
    Верхняя оценка числа баров MOEX в окне по календарю (будни × типичная плотность).

    Нужна для детекта «в кеше меньше баров, чем ожидается по календарю»; завышение
    допустимо — тогда сработает slack при сравнении с фактом.
    """
    c = (canonical_interval or "").strip()
    if c not in CANONICAL_TO_MOEX:
        raise ValueError(f"unknown interval: {canonical_interval}")
    a, b = _utc(from_ts), _utc(to_ts)
    if b <= a:
        return 0
    d0, d1 = a.date(), b.date()
    w = count_weekdays_in_date_range(d0, d1)
    per = _BARS_PER_WEEKDAY_UPPER.get(c, 1.0)
    if c == "1w":
        days = max(0, (b - a).days)
        return max(1, int(days / 7) + 1)
    if c == "1M":
        months = (d1.year - d0.year) * 12 + (d1.month - d0.month) + 1
        return max(1, months)
    return max(0, int(w * per) + 1)


def count_slack_for_expected(expected: int) -> int:
    """Допуск к ожидаемому числу баров (праздники, укороченные дни, расхождение с MOEX)."""
    if expected <= 0:
        return 0
    return max(2, min(int(expected * 0.18) + 3, int(expected * 0.35)))


def count_bucket_starts_in_closed_interval(
        sorted_times: Sequence[datetime],
        lo: datetime,
        hi: datetime,
) -> int:
    """Число элементов в sorted_times с lo <= t <= hi."""
    if not sorted_times:
        return 0
    i = bisect.bisect_left(sorted_times, lo)
    j = bisect.bisect_right(sorted_times, hi)
    return j - i


def _heuristic_time_gap_raw(
        times: List[datetime],
        from_ts: datetime,
        to_ts: datetime,
        thr: timedelta,
) -> List[Tuple[datetime, datetime]]:
    raw: List[Tuple[datetime, datetime]] = []
    if not times:
        raw.append((from_ts, to_ts))
        return raw
    if times[0] > from_ts:
        raw.append((from_ts, times[0]))
    for i in range(1, len(times)):
        delta = times[i] - times[i - 1]
        if delta > thr:
            raw.append((times[i - 1], times[i]))
    if times[-1] < to_ts:
        raw.append((times[-1], to_ts))
    return raw


def daily_weekday_calendar_gap_ranges(
        existing_sorted: Sequence[datetime],
        from_ts: datetime,
        to_ts: datetime,
) -> List[Tuple[datetime, datetime]]:
    """
    Для дневных свечей: отрезки времени, где по календарю ожидается будний торговый день,
    а в кеше нет бара с датой bucket_start (UTC date).
    """
    a, b = _utc(from_ts), _utc(to_ts)
    if b <= a:
        return []
    have = {_utc(t).date() for t in existing_sorted}
    d0, d1 = a.date(), b.date()
    out: List[Tuple[datetime, datetime]] = []
    cur_first: date | None = None
    d = d0
    while d <= d1:
        is_wd = d.weekday() < 5
        missing = is_wd and (d not in have)
        if missing:
            if cur_first is None:
                cur_first = d
        elif cur_first is not None:
            st = datetime.combine(cur_first, time.min, tzinfo=timezone.utc)
            en = datetime.combine(d, time.min, tzinfo=timezone.utc)
            out.append((st, en))
            cur_first = None
        d += timedelta(days=1)
    if cur_first is not None:
        st = datetime.combine(cur_first, time.min, tzinfo=timezone.utc)
        en = datetime.combine(d1 + timedelta(days=1), time.min, tzinfo=timezone.utc)
        out.append((st, en))
    return [(x, y) for x, y in out if y > x]


def intraday_calendar_chunk_gap_ranges(
        sorted_times: List[datetime],
        from_ts: datetime,
        to_ts: datetime,
        canonical_interval: str,
        *,
        num_chunks: int = 48,
) -> List[Tuple[datetime, datetime]]:
    """
    Если фактическое число баров заметно ниже календарной верхней оценки, ищем подокна
    по времени, где плотность баров в кеше ниже ожидаемой (пропорция будней в чанке).
    """
    a, b = _utc(from_ts), _utc(to_ts)
    if b <= a:
        return []
    exp_total = expected_bar_count_upper_bound(a, b, canonical_interval)
    slack_total = count_slack_for_expected(exp_total)
    if len(sorted_times) >= exp_total - slack_total:
        return []

    total_sec = (b - a).total_seconds()
    raw: List[Tuple[datetime, datetime]] = []
    for i in range(num_chunks):
        lo = a + timedelta(seconds=total_sec * i / num_chunks)
        hi = a + timedelta(seconds=total_sec * (i + 1) / num_chunks)
        exp_c = expected_bar_count_upper_bound(lo, hi, canonical_interval)
        if exp_c < 1:
            continue
        act = count_bucket_starts_in_closed_interval(sorted_times, lo, hi)
        slack_c = max(0, int(0.12 * exp_c))
        if act < exp_c - slack_c:
            raw.append((lo, hi))
    return merge_ranges(raw)


def compute_moex_fetch_ranges(
        existing_sorted: Sequence[datetime],
        from_ts: datetime,
        to_ts: datetime,
        canonical_interval: str,
) -> List[Tuple[datetime, datetime]]:
    """
    Возвращает список отрезков [start, end] для вызова fetch_moex_candles_range
    (границы окна job: ``from_ts`` … ``to_ts`` включительно для баров в БД).

    ``existing_sorted`` — все ``bucket_start`` в этом окне, по возрастанию.

    Для ``1d`` дополнительно используется календарь будних дней без бара в кеше.
    Для прочих интервалов при недоборе баров относительно ожидаемого максимума —
    нарезка окна на чанки и дозапрос участков с низкой плотностью.
    """
    if from_ts >= to_ts:
        return []

    interval = (canonical_interval or "").strip()
    if interval not in CANONICAL_TO_MOEX:
        raise ValueError(f"unknown interval: {canonical_interval}")

    thr = internal_gap_threshold(interval)
    a0, b0 = _utc(from_ts), _utc(to_ts)
    times = sorted({_utc(t) for t in existing_sorted})
    from_ts, to_ts = a0, b0

    if not times:
        return [(from_ts, to_ts)] if to_ts > from_ts else []

    raw: List[Tuple[datetime, datetime]] = []

    if interval == "1d":
        raw.extend(daily_weekday_calendar_gap_ranges(times, from_ts, to_ts))
    else:
        raw.extend(_heuristic_time_gap_raw(times, from_ts, to_ts, thr))
        raw.extend(
            intraday_calendar_chunk_gap_ranges(
                times, from_ts, to_ts, interval,
            ),
        )

    merged = merge_ranges(raw)
    return [(a, b) for a, b in merged if b > a]
