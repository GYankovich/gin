"""In-memory backtest run registry (Stage 3b MVP)."""

from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class BacktestRunRecord:
    run_id: int
    user_id: int
    robot_id: int | None
    status: str
    requested_from: datetime
    requested_to: datetime
    started_at: datetime
    finished_at: datetime | None = None
    initial_capital: float = 0.0
    progress_percent: float = 0.0
    run_phase: str = "queued"
    phase_label: str = "Queued"
    phase_units_done: int = 0
    phase_units_total: int = 0
    cancel_requested: bool = False
    error_message: str | None = None
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    result_payload: dict[str, Any] = field(default_factory=dict)
    portfolio_snapshots: list[dict[str, Any]] = field(default_factory=list)
    signals: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    daily_summary: list[dict[str, Any]] = field(default_factory=list)


class BacktestRunStore:
    def __init__(self) -> None:
        self._runs: dict[int, BacktestRunRecord] = {}
        self._lock = asyncio.Lock()
        self._id_gen = itertools.count(1)

    async def create(
        self,
        *,
        user_id: int,
        robot_id: int | None,
        requested_from: datetime,
        requested_to: datetime,
        initial_capital: float,
        config_snapshot: dict[str, Any],
    ) -> BacktestRunRecord:
        async with self._lock:
            run_id = next(self._id_gen)
            now = datetime.now(timezone.utc)
            rec = BacktestRunRecord(
                run_id=run_id,
                user_id=user_id,
                robot_id=robot_id,
                status="QUEUED",
                requested_from=requested_from,
                requested_to=requested_to,
                started_at=now,
                initial_capital=initial_capital,
                config_snapshot=config_snapshot,
            )
            self._runs[run_id] = rec
            return rec

    async def get(self, run_id: int, *, user_id: int | None = None) -> BacktestRunRecord | None:
        async with self._lock:
            rec = self._runs.get(run_id)
            if rec is None:
                return None
            if user_id is not None and rec.user_id != user_id:
                return None
            return rec

    async def update(self, run_id: int, **fields: Any) -> BacktestRunRecord | None:
        async with self._lock:
            rec = self._runs.get(run_id)
            if rec is None:
                return None
            for key, value in fields.items():
                if hasattr(rec, key):
                    setattr(rec, key, value)
            return rec

    async def rebind_id(self, old_id: int, new_id: int) -> BacktestRunRecord | None:
        async with self._lock:
            rec = self._runs.pop(old_id, None)
            if rec is None:
                return None
            rec.run_id = new_id
            self._runs[new_id] = rec
            return rec
        async with self._lock:
            rec = self._runs.get(run_id)
            if rec is None or rec.user_id != user_id:
                return None
            rec.cancel_requested = True
            if rec.status in ("QUEUED", "RUNNING"):
                rec.run_phase = "cancel_pending"
                rec.phase_label = "Cancel requested"
            return rec


backtest_run_store = BacktestRunStore()
