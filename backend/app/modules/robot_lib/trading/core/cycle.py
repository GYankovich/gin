"""Типы одного торгового цикла (ядро)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CycleStatsDelta:
    """Счётчики, обновлённые за цикл (для тестов / метрик)."""

    signals_generated: int = 0
    orders_placed: int = 0
