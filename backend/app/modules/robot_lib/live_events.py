"""No-op live-event helpers (legacy robot_session_logs / NOTIFY retired in Wave 2/3).

Kept as import surface for TradingSession / session_backtest until that stack
moves fully to robots.
"""
from __future__ import annotations

from typing import Any


def uses_postgres_live_events() -> bool:
    return False


def notify_robot_live_event(*_args: Any, **_kwargs: Any) -> None:
    return None


def notify_live_alert(*_args: Any, **_kwargs: Any) -> None:
    return None


def notify_live_prices(*_args: Any, **_kwargs: Any) -> None:
    return None


def notify_live_orders_refresh(*_args: Any, **_kwargs: Any) -> None:
    return None


def publish_live_event(*_args: Any, **_kwargs: Any) -> None:
    return None


def insert_session_log(*_args: Any, **_kwargs: Any) -> None:
    return None


def fetch_recent_session_logs(*_args: Any, **_kwargs: Any) -> list:
    return []


def expand_inline_live_payload(payload: Any) -> Any:
    return payload


class PgLiveEventSubscriber:
    """Retired — tables/NOTIFY path removed."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None
