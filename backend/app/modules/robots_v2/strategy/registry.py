"""Strategy plugin registry."""

from __future__ import annotations

from typing import Callable, Type

from app.modules.robots_v2.config.v4_schema import StrategyArchetype
from app.modules.robots_v2.strategy.base import StrategyPlugin
from app.modules.robots_v2.strategy.plugins.grid import GridPlugin
from app.modules.robots_v2.strategy.plugins.momentum import MomentumPlugin
from app.modules.robots_v2.strategy.plugins.reversion import ReversionPlugin
from app.modules.robots_v2.strategy.plugins.scalper import ScalperPlugin
from app.modules.robots_v2.strategy.schemas import ArchetypeInfo

_PLUGIN_FACTORIES: dict[StrategyArchetype, Callable[[], StrategyPlugin]] = {
    "scalper": ScalperPlugin,
    "momentum": MomentumPlugin,
    "reversion": ReversionPlugin,
    "grid": GridPlugin,
}


def create_plugin(archetype: StrategyArchetype) -> StrategyPlugin:
    factory = _PLUGIN_FACTORIES.get(archetype)
    if factory is None:
        raise KeyError(f"Unknown strategy archetype: {archetype}")
    return factory()


def list_archetypes() -> list[ArchetypeInfo]:
    plugins: list[tuple[Type[StrategyPlugin], StrategyArchetype]] = [
        (ScalperPlugin, "scalper"),
        (MomentumPlugin, "momentum"),
        (ReversionPlugin, "reversion"),
        (GridPlugin, "grid"),
    ]
    out: list[ArchetypeInfo] = []
    for cls, archetype in plugins:
        inst = cls()
        out.append(ArchetypeInfo(
            archetype=archetype,
            required_data=inst.required_data,
            warmup_bars=inst.warmup_bars,
            entry_triggers=inst.entry_triggers,
            requires_websocket=archetype == "scalper",
        ))
    return out
