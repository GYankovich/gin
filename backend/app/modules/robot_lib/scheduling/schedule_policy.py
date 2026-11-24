"""
Проверка robot_schedules для запуска LIVE-сессий (BRD-ARCH-04 этап 5).

Битовая маска weekdays: 1=пн … 32=вс (как в UI и Stage6).
Время start_time/end_time — MSK (timetz +03 из БД).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore

_MSK = ZoneInfo("Europe/Moscow") if ZoneInfo else timezone(timedelta(hours=3))

_DEFAULT_MARKET_START = "10:00"
_DEFAULT_MARKET_END = "18:45"
_DEFAULT_WEEKDAYS = 31


def _now_msk(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(_MSK)


def _parse_hhmm(value: Any) -> Optional[tuple[int, int]]:
    if value is None:
        return None
    if isinstance(value, datetime):
        t = value.timetz() if hasattr(value, "timetz") else value.time()
        return t.hour, t.minute
    if isinstance(value, time):
        return value.hour, value.minute
    s = str(value).strip()
    if "T" in s:
        s = s.split("T", 1)[1]
    part = s[:8]
    try:
        hh, mm, *_ = part.replace("+", ":").split(":")
        return int(hh), int(mm)
    except Exception:
        return None


def _minutes_msk(now_utc: datetime) -> int:
    msk = _now_msk(now_utc)
    return msk.hour * 60 + msk.minute


def _weekday_allowed(now_utc: datetime, weekdays: int) -> bool:
    mask = int(weekdays or 0)
    if mask <= 0:
        return True
    return bool(mask & (1 << now_utc.weekday()))


def _time_window_allowed(now_utc: datetime, start: Any, end: Any) -> bool:
    st = _parse_hhmm(start)
    et = _parse_hhmm(end)
    if not st or not et:
        return True
    cur = _minutes_msk(now_utc)
    start_m = st[0] * 60 + st[1]
    end_m = et[0] * 60 + et[1]
    if start_m <= end_m:
        return start_m <= cur <= end_m
    return cur >= start_m or cur <= end_m


def schedule_dict_from_robot(robot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    st = robot.get("schedule_type")
    cfg = robot.get("config") or {}
    broker_type = str(cfg.get("broker_type") or "").strip().lower()
    if st is not None or robot.get("start_time") is not None:
        return {
            "schedule_type": st,
            "interval_seconds": robot.get("interval_seconds"),
            "start_time": robot.get("start_time"),
            "end_time": robot.get("end_time"),
            "weekdays": robot.get("weekdays"),
        }
    if broker_type == "bybit":
        # Crypto 24/7: без robot_schedules работаем в always-on режиме.
        return {"schedule_type": 1}
    risk = cfg.get("risk") or {}
    if risk.get("trading_hours_start") or risk.get("trading_hours_end"):
        return {
            "schedule_type": 2,
            "start_time": risk.get("trading_hours_start", _DEFAULT_MARKET_START),
            "end_time": risk.get("trading_hours_end", _DEFAULT_MARKET_END),
            "weekdays": int(risk.get("allowed_weekdays") or _DEFAULT_WEEKDAYS),
        }
    return None


def inside_schedule_window(
    now_utc: datetime,
    schedule: Optional[Dict[str, Any]],
) -> bool:
    if not schedule:
        return True
    schedule_type = int(schedule.get("schedule_type") or 2)
    if schedule_type == 1:
        return True
    if not _weekday_allowed(now_utc, int(schedule.get("weekdays") or 0)):
        return False
    if schedule_type == 3:
        return _time_window_allowed(
            now_utc, _DEFAULT_MARKET_START, _DEFAULT_MARKET_END
        ) and _weekday_allowed(now_utc, _DEFAULT_WEEKDAYS)
    return _time_window_allowed(
        now_utc, schedule.get("start_time"), schedule.get("end_time")
    )


def should_start_trading_session(
    robot: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> bool:
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    schedule = schedule_dict_from_robot(robot)
    return inside_schedule_window(now_utc, schedule)


__all__ = [
    "inside_schedule_window",
    "schedule_dict_from_robot",
    "should_start_trading_session",
]
