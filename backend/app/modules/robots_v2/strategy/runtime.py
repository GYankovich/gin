"""Strategy Runtime — session-scoped plugin orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.modules.robots.trading.contracts import Position, Signal
from app.modules.robots_v2.config.v4_schema import StrategyArchetype, StrategyConfig
from app.modules.robots_v2.strategy.base import StrategyPlugin
from app.modules.robots_v2.strategy.registry import create_plugin, list_archetypes
from app.modules.robots_v2.strategy.schemas import ArchetypeInfo, StrategyContext


class StrategyRuntime:
    """Stateful runtime: one plugin instance per trading session."""

    def __init__(self) -> None:
        self._sessions: dict[int, StrategyPlugin] = {}

    def get_plugin(self, session_id: int, archetype: StrategyArchetype) -> StrategyPlugin:
        plugin = self._sessions.get(session_id)
        if plugin is None or plugin.archetype != archetype:
            plugin = create_plugin(archetype)
            self._sessions[session_id] = plugin
        return plugin

    def drop_session(self, session_id: int) -> None:
        self._sessions.pop(session_id, None)

    def evaluate(self, session_id: int, ctx: StrategyContext) -> list[Signal]:
        plugin = self.get_plugin(session_id, ctx.config.archetype)
        signals = plugin.evaluate(ctx)
        return self._order_exits_first(signals)

    def last_scan(self, session_id: int, archetype: StrategyArchetype) -> list[dict[str, Any]]:
        plugin = self._sessions.get(session_id)
        if plugin is None or plugin.archetype != archetype:
            return []
        return plugin.last_scan

    def on_universe_change(
        self,
        session_id: int,
        archetype: StrategyArchetype,
        added: list[str],
        removed: list[str],
        open_positions: list[Position],
    ) -> None:
        plugin = self.get_plugin(session_id, archetype)
        plugin.on_universe_change(added, removed, open_positions)

    def notify_stop_loss(
        self,
        session_id: int,
        archetype: StrategyArchetype,
        ticker: str,
        *,
        at: datetime | None = None,
    ) -> None:
        plugin = self._sessions.get(session_id)
        if plugin is None or plugin.archetype != archetype:
            return
        plugin.on_stop_loss(ticker, at=at)

    @staticmethod
    def _order_exits_first(signals: list[Signal]) -> list[Signal]:
        exits = [s for s in signals if s.side == "CLOSE" or str((s.meta or {}).get("kind", "")).startswith("exit")]
        entries = [s for s in signals if s not in exits]
        return exits + entries

    @staticmethod
    def archetypes() -> list[ArchetypeInfo]:
        return list_archetypes()


strategy_runtime = StrategyRuntime()
