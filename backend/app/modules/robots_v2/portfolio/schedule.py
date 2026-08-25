"""Schedule gate for robots_v2 portfolio updaters (config.schedule v4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.modules.robots_v2.config.v4_schema import ScheduleConfig
from app.modules.robots_v2.risk.eod import is_within_trading_session

_POLL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}


def poll_interval_seconds(poll: str | None) -> int:
    return _POLL_SECONDS.get(str(poll or "5m"), 300)


def schedule_from_config(config: dict[str, Any] | None) -> ScheduleConfig | None:
    if not isinstance(config, dict):
        return None
    raw = config.get("schedule")
    if not isinstance(raw, dict):
        return None
    try:
        return ScheduleConfig.model_validate(raw)
    except Exception:
        return None


def should_run_portfolio(
    config: dict[str, Any] | None,
    last_started: datetime | None,
    *,
    now: datetime | None = None,
) -> tuple[bool, str | None]:
    """True when inside schedule window and poll interval elapsed."""
    schedule = schedule_from_config(config)
    if schedule is None:
        return True, None

    now_utc = now or datetime.now(timezone.utc)
    if not is_within_trading_session(schedule, now=now_utc):
        return False, "вне временного окна расписания"

    interval = poll_interval_seconds(schedule.poll_interval)
    if interval <= 0 or last_started is None:
        return True, None

    started = last_started
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    elapsed = (now_utc - started).total_seconds()
    if elapsed >= interval:
        return True, None
    return False, f"интервал {interval}с не достигнут (прошло {elapsed:.0f}с)"
