"""Engine types."""

from __future__ import annotations

import re
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


# Ordered pipeline stages for monitor progress (0..N-1).
CYCLE_STAGES: tuple[str, ...] = (
    "idle",
    "prices",
    "reconcile",
    "schedule",
    "exits",
    "strategy",
    "risk",
    "execution",
    "metrics",
    "done",
)

CYCLE_STAGE_LABELS: dict[str, str] = {
    "idle": "Ожидание",
    "prices": "Цены",
    "reconcile": "Сверка",
    "schedule": "Расписание",
    "exits": "Выходы SL/TP",
    "strategy": "Стратегия",
    "risk": "Риск",
    "execution": "Исполнение",
    "metrics": "Метрики",
    "done": "Цикл завершён",
    "skipped": "Пропуск",
    "bootstrap": "Bootstrap",
    "bootstrap_sync": "Синхронизация",
}


def cycle_stage_progress(stage: str, detail: str | None = None) -> float:
    if stage in ("skipped", "done"):
        return 1.0
    # Bootstrap / sync: advance by sub-step so the monitor is not stuck at 5%.
    if stage == "bootstrap":
        d = (detail or "").lower()
        if d.startswith("atr_warmup"):
            m = re.match(r"atr_warmup\s+(\d+)/(\d+)", d)
            if m:
                cur, tot = int(m.group(1)), max(int(m.group(2)), 1)
                return round(0.08 + 0.14 * (cur / tot), 3)
            return 0.10
        if d.startswith("moex_snapshot") or d == "screener_filters":
            return 0.06
        if d.startswith("universe"):
            if "retry" in d:
                return 0.06
            return 0.08
        if "seed" in d or "candle" in d:
            return 0.22
        if "reconcil" in d:
            return 0.40
        return 0.12
    if stage == "bootstrap_sync":
        d = (detail or "").lower()
        if d.startswith("attempt"):
            return 0.48
        if d == "prices":
            return 0.58
        if "reconcil" in d:
            return 0.72
        if d == "orders":
            return 0.88
        return 0.50
    try:
        idx = CYCLE_STAGES.index(stage)
    except ValueError:
        return 0.0
    if len(CYCLE_STAGES) <= 1:
        return 0.0
    return round(idx / (len(CYCLE_STAGES) - 1), 3)


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
    last_prices_at: datetime | None = None
    ws_healthy: bool = True
    message: str | None = None
    decisions: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    cycle_stage: str = "idle"
    cycle_progress: float = 0.0
    cycle_detail: str | None = None
    cycle_skip_reason: str | None = None
    last_triggered_by: str | None = None
    last_ticker_scan: list[dict[str, Any]] = field(default_factory=list)
    last_ticker_scan_at: datetime | None = None
    open_orders: list[dict[str, Any]] = field(default_factory=list)
    bootstrap_ready: bool = False
    universe_refreshed_at: datetime | None = None
