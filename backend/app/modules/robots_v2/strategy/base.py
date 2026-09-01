"""Base class for Strategy Runtime plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.modules.robots.trading.contracts import Position, Signal
from app.modules.robots_v2.config.v4_schema import StrategyArchetype
from app.modules.robots_v2.strategy.schemas import (
    DataRequirement,
    StrategyContext,
    StrategySessionState,
    TriggeredBy,
)


class StrategyPlugin(ABC):
    archetype: StrategyArchetype
    required_data: list[DataRequirement]
    warmup_bars: int
    entry_triggers: list[TriggeredBy]

    def __init__(self) -> None:
        self._state = StrategySessionState(archetype=self.archetype)
        self._last_scan: list[dict[str, Any]] = []
        self.scan_enabled = True

    @property
    def last_scan(self) -> list[dict[str, Any]]:
        return list(self._last_scan)

    def _begin_scan(self) -> None:
        if not self.scan_enabled:
            return
        self._last_scan = []

    def _record_scan(
        self,
        ticker: str,
        *,
        code: str,
        message: str,
        price: float | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        if not self.scan_enabled:
            return
        row: dict[str, Any] = {
            "ticker": ticker.upper(),
            "code": code,
            "message": message,
        }
        if price is not None and price > 0:
            row["price"] = round(float(price), 4)
        if metrics:
            row["metrics"] = metrics
        self._last_scan.append(row)

    @property
    def state(self) -> StrategySessionState:
        return self._state

    def ticker_state(self, ticker: str) -> dict[str, Any]:
        t = ticker.upper()
        if t not in self._state.per_ticker:
            self._state.per_ticker[t] = {}
        return self._state.per_ticker[t]

    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        ...

    def on_universe_change(self, added: list[str], removed: list[str], open_positions: list[Position]) -> None:
        held = {str(p.secid or p.figi or "").upper() for p in open_positions if p.quantity > 0}
        for t in removed:
            key = t.upper()
            if key not in held:
                self._state.per_ticker.pop(key, None)

        for t in added:
            key = t.upper()
            if key not in self._state.per_ticker:
                self._state.per_ticker[key] = {}

    def on_position_opened(self, position: Position) -> None:
        return None

    def on_position_closed(self, position: Position) -> None:
        ticker = str(position.secid or position.figi or "").upper()
        if ticker:
            self._state.per_ticker.pop(ticker, None)

    def on_stop_loss(self, ticker: str, *, at: datetime | None = None, price: float | None = None) -> None:
        """Called after a stop-loss / invalidation fill — plugins may pause re-entry on this ticker."""
        t = ticker.upper()
        ts = self.ticker_state(t)
        ts["lastSlAt"] = at or datetime.now(timezone.utc)
        if price is not None:
            try:
                px = float(price)
            except (TypeError, ValueError):
                px = 0.0
            if px > 0:
                ts["lastCutPrice"] = px

    def _in_universe(self, ctx: StrategyContext, ticker: str) -> bool:
        u = {t.upper() for t in ctx.universe}
        return ticker.upper() in u

    def _warmup_ok(self, candles: list, ticker: str) -> bool:
        return len(candles or []) >= self.warmup_bars
