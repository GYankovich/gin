"""EOD flatten helpers (MOEX stocks default on)."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    MSK = ZoneInfo("Europe/Moscow")
except Exception:  # pragma: no cover
    MSK = timezone(timedelta(hours=3), name="MSK")

from app.modules.robots_v2.config.v4_schema import RiskConfig, ScheduleConfig



def _parse_hhmm(raw: str) -> time:
    parts = str(raw or "18:30").split(":")
    h = int(parts[0]) if parts else 18
    m = int(parts[1]) if len(parts) > 1 else 0
    return time(hour=h, minute=m)


def minutes_to_session_close(schedule: ScheduleConfig, *, now: datetime | None = None) -> float | None:
    """Minutes until schedule.timeTo in MSK today. None if outside weekday or already past close."""
    now_msk = (now or datetime.now(timezone.utc)).astimezone(MSK)
    # weekdays[0]=Mon … [6]=Sun
    wd = now_msk.weekday()
    if wd >= len(schedule.weekdays) or not schedule.weekdays[wd]:
        return None
    close_t = _parse_hhmm(schedule.time_to)
    close_dt = datetime.combine(now_msk.date(), close_t, tzinfo=MSK)
    delta = (close_dt - now_msk).total_seconds() / 60.0
    return delta


def should_eod_flatten(
    *,
    risk: RiskConfig,
    schedule: ScheduleConfig,
    instrument_type: str,
    now: datetime | None = None,
) -> bool:
    if not risk.eod_flatten_enabled_for(instrument_type):  # type: ignore[arg-type]
        return False
    mins = minutes_to_session_close(schedule, now=now)
    if mins is None:
        return False
    threshold = int(risk.eod_flatten.minutes_before_close)
    # Inside window: 0 < minutes_to_close <= threshold (also flatten if slightly past close)
    return mins <= threshold
