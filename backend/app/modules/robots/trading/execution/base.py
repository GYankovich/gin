"""
Абстрактный Execution — общий контракт исполнения ордеров.

См. docs/BRD-ARCH-03-unified-engine-architecture.md §8.
"""
#///EPIC Modules.ITEM Module.TOPIC BackendAppModulesRobotsTradingExecutionBase [1]
#/// Исходный модуль `backend/app/modules/robots/trading/execution/base.py` — автоматическая разметка для Obsidian Source Scanner.

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional
from uuid import UUID

from app.modules.robots.trading.contracts import Fill, Order


@dataclass
class ExecutionResult:
    """Результат `Execution.submit` — содержит обновлённый Order и Fill (если был)."""
    order: Order
    fill: Optional[Fill] = None
    accepted: bool = True
    reject_reason: str = ""


class Execution(ABC):
    """Контракт исполнения ордеров (sim / live).

    Реализации:
    - `SimExecution` — backtest;
    - `LiveExecution` — реальная торговля через `BrokerFacade`.
    """

    @abstractmethod
    async def submit(self, order: Order, **context) -> ExecutionResult:
        """Отправляет ордер и возвращает результат (fill или reject).

        `context` — дополнительные данные для исполнителя (например, серия свечей
        для sim-варианта, чтобы определить цену исполнения).
        """

    async def cancel(self, order_id: UUID) -> bool:
        """Отменяет ордер. По умолчанию — no-op."""
        return False

    async def on_state_changed(self) -> AsyncIterator[Order]:
        """Поток обновлений статусов ордеров (live-only)."""
        raise NotImplementedError("on_state_changed is live-only")


__all__ = ["Execution", "ExecutionResult"]
