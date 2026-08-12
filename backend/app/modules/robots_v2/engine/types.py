"""Engine types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SessionState(str, Enum):
    BOOTSTRAP = "BOOTSTRAP"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    TERMINATED = "TERMINATED"
    ERROR = "ERROR"


def poll_interval_seconds(raw: str) -> int:
    mapping = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
    return mapping.get(str(raw or "5m"), 300)


@dataclass
class SessionStatus:
    robot_id: int
    session_state: SessionState
    mode: str
    cycle_number: int = 0
    equity: float = 0.0
    cash: float = 0.0
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    universe: list[str] = field(default_factory=list)
    last_cycle_at: datetime | None = None
    ws_healthy: bool = True
    message: str | None = None
    decisions: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
